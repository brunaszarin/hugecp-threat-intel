"""Carga dos CSVs no banco.

A ingestão é idempotente por construção: tudo acontece numa única transação que
esvazia as tabelas e recarrega os arquivos. Rodar N vezes produz sempre o mesmo
estado, e quem consulta o banco durante a carga continua vendo os dados antigos
até o COMMIT.
"""

from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

import psycopg

FLOWS_COLUMNS = (
    "timestamp",
    "src_ip",
    "src_port",
    "dst_ip",
    "dst_port",
    "protocol",
    "bytes",
    "packets",
    "src_asn",
    "src_country",
)
INDICATORS_COLUMNS = (
    "indicator",
    "category",
    "source",
    "confidence",
    "first_seen",
    "last_seen",
)
COPY_CHUNK_SIZE = 1 << 16


class IngestError(Exception):
    """Erro de validação dos arquivos de entrada."""


@dataclass(frozen=True)
class IngestResult:
    flows: int
    origins: int
    indicators: int


def schema_sql() -> str:
    return files("app.db").joinpath("schema.sql").read_text(encoding="utf-8")


def _check_header(path: Path, expected: tuple[str, ...]) -> None:
    if not path.is_file():
        raise IngestError(f"Arquivo não encontrado: {path}")
    with path.open(encoding="utf-8", newline="") as fh:
        header = tuple(col.strip() for col in fh.readline().split(","))
    if header != expected:
        raise IngestError(f"Cabeçalho inesperado em {path.name}: {header}. Esperado: {expected}")


def _copy_file(cur: psycopg.Cursor[tuple[object, ...]], table: str, path: Path) -> None:
    # COPY em modo CSV aceita tanto \n quanto \r\n (os arquivos fornecidos usam \r\n).
    with (
        cur.copy(f"COPY {table} FROM STDIN WITH (FORMAT csv, HEADER true)") as copy,
        path.open("rb") as fh,
    ):
        while chunk := fh.read(COPY_CHUNK_SIZE):
            copy.write(chunk)


def _count(cur: psycopg.Cursor[tuple[object, ...]], table: str) -> int:
    row = cur.execute(f"SELECT count(*) FROM {table}").fetchone()
    assert row is not None
    return int(str(row[0]))


def run_ingest(
    conn: psycopg.Connection[tuple[object, ...]], flows_path: Path, indicators_path: Path
) -> IngestResult:
    _check_header(flows_path, FLOWS_COLUMNS)
    _check_header(indicators_path, INDICATORS_COLUMNS)

    with conn.transaction(), conn.cursor() as cur:
        cur.execute(schema_sql())

        # Staging em texto/bigint: a conversão e a validação de tipos (inet,
        # CHECKs) acontecem no INSERT final, com mensagens de erro do Postgres.
        cur.execute(
            """
            CREATE TEMP TABLE staging_flows (
                timestamp bigint, src_ip text, src_port integer, dst_ip text,
                dst_port integer, protocol text, bytes bigint, packets bigint,
                src_asn integer, src_country text
            ) ON COMMIT DROP;
            CREATE TEMP TABLE staging_indicators (
                indicator text, category text, source text, confidence smallint,
                first_seen bigint, last_seen bigint
            ) ON COMMIT DROP;
            """
        )
        _copy_file(cur, "staging_flows", flows_path)
        _copy_file(cur, "staging_indicators", indicators_path)

        cur.execute("TRUNCATE flows, origins, indicators RESTART IDENTITY")

        # Se um mesmo IP vier com ASN ou país diferentes, o DISTINCT gera duas
        # linhas para o mesmo IP e a PK falha: preferimos falhar alto a escolher
        # um valor arbitrário.
        cur.execute(
            """
            INSERT INTO origins (ip, asn, country)
            SELECT DISTINCT src_ip::inet, src_asn, src_country
            FROM staging_flows
            """
        )
        cur.execute(
            """
            INSERT INTO flows (ts, src_ip, src_port, dst_ip, dst_port,
                               protocol, bytes, packets)
            SELECT to_timestamp(timestamp), src_ip::inet, src_port, dst_ip::inet,
                   dst_port, protocol, bytes, packets
            FROM staging_flows
            """
        )
        cur.execute(
            """
            INSERT INTO indicators (ip, category, source, confidence,
                                    first_seen, last_seen)
            SELECT indicator::inet, category, source, confidence,
                   to_timestamp(first_seen), to_timestamp(last_seen)
            FROM staging_indicators
            """
        )

        result = IngestResult(
            flows=_count(cur, "flows"),
            origins=_count(cur, "origins"),
            indicators=_count(cur, "indicators"),
        )

    # Atualiza estatísticas do planejador depois da carga (fora da transação).
    with conn.cursor() as cur:
        cur.execute("ANALYZE flows, origins, indicators")

    return result
