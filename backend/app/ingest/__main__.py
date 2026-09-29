"""Comando de ingestão: `uv run python -m app.ingest --data-dir ../data`."""

import argparse
import sys
import time
from pathlib import Path

import psycopg

from app.core.config import settings
from app.ingest.loader import IngestError, run_ingest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Carrega flows e indicadores no banco.")
    parser.add_argument("--data-dir", type=Path, default=Path("../data"))
    parser.add_argument("--flows", type=Path, help="Padrão: <data-dir>/flows.csv")
    parser.add_argument("--indicators", type=Path, help="Padrão: <data-dir>/indicadores.csv")
    parser.add_argument("--database-url", default=settings.database_url)
    args = parser.parse_args(argv)

    flows_path: Path = args.flows or args.data_dir / "flows.csv"
    indicators_path: Path = args.indicators or args.data_dir / "indicadores.csv"

    started = time.perf_counter()
    try:
        with psycopg.connect(args.database_url) as conn:
            result = run_ingest(conn, flows_path, indicators_path)
    except IngestError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    except psycopg.OperationalError as exc:
        print(f"Não foi possível conectar ao banco: {exc}", file=sys.stderr)
        print("O banco está rodando? Tente `make db-up`.", file=sys.stderr)
        return 1

    elapsed = time.perf_counter() - started
    print(
        f"Ingestão concluída em {elapsed:.1f}s: {result.flows} flows, "
        f"{result.origins} origens, {result.indicators} indicadores."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
