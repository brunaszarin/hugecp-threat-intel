"""Consultas das origens: lista de origens que merecem atenção (B) e ficha (C).

Os critérios são exatamente os do enunciado e são calculados dentro do período
filtrado. ICMP não tem portas, então fica fora das contagens de portas.
"""

from ipaddress import IPv4Address
from typing import Any, Literal

import psycopg
from psycopg.rows import dict_row

from app.repositories.time_range import TimeRange

Conn = psycopg.Connection[Any]

Criterion = Literal["indicator", "many_destinations", "many_ports", "top_bytes"]
CRITERIA: tuple[Criterion, ...] = ("indicator", "many_destinations", "many_ports", "top_bytes")

# Limiares do enunciado. "Mais de N" é estritamente maior.
MIN_DESTINATIONS_EXCLUSIVE = 20
MIN_PORTS_PER_DESTINATION_EXCLUSIVE = 50
TOP_BYTES_LIMIT = 20

OriginSort = Literal[
    "bytes", "packets", "flows", "destinations", "ports", "first_seen", "last_seen", "confidence"
]
FlowSort = Literal["ts", "bytes", "packets"]
SortOrder = Literal["asc", "desc"]


def _origin_stats_sql() -> str:
    """CTE com as estatísticas de todas as origens do período e os critérios acionados.

    O "top 20 em bytes" depende do conjunto inteiro de origens, por isso a ficha de
    um único IP também passa por aqui antes de filtrar.
    """
    return """
        WITH period_flows AS (
            SELECT * FROM flows WHERE ts >= %(start)s AND ts < %(end)s
        ),
        per_source AS (
            SELECT src_ip,
                   sum(bytes)::bigint                                   AS bytes,
                   sum(packets)::bigint                                 AS packets,
                   count(*)                                             AS flows,
                   count(DISTINCT dst_ip)                               AS destinations,
                   count(DISTINCT dst_port) FILTER (WHERE protocol <> 'ICMP') AS ports,
                   min(ts)                                              AS first_seen,
                   max(ts)                                              AS last_seen
            FROM period_flows
            GROUP BY src_ip
        ),
        ports_per_destination AS (
            SELECT src_ip, max(n) AS max_ports_per_destination
            FROM (
                SELECT src_ip, dst_ip, count(DISTINCT dst_port) AS n
                FROM period_flows
                WHERE protocol <> 'ICMP'
                GROUP BY src_ip, dst_ip
            ) AS by_pair
            GROUP BY src_ip
        ),
        origin_stats AS (
            SELECT s.*,
                   coalesce(p.max_ports_per_destination, 0) AS max_ports_per_destination,
                   o.asn, o.country,
                   i.category, i.source, i.confidence,
                   i.first_seen AS indicator_first_seen,
                   i.last_seen  AS indicator_last_seen,
                   -- rank() inclui empates na 20ª posição em vez de escolher um ao acaso.
                   rank() OVER (ORDER BY s.bytes DESC) AS bytes_rank,
                   i.ip IS NOT NULL AS is_indicator
            FROM per_source s
            JOIN origins o ON o.ip = s.src_ip
            LEFT JOIN ports_per_destination p ON p.src_ip = s.src_ip
            LEFT JOIN indicators i ON i.ip = s.src_ip
        ),
        with_criteria AS (
            SELECT *,
                   array_remove(ARRAY[
                       CASE WHEN is_indicator THEN 'indicator' END,
                       CASE WHEN destinations > %(min_destinations)s
                            THEN 'many_destinations' END,
                       CASE WHEN max_ports_per_destination > %(min_ports)s
                            THEN 'many_ports' END,
                       CASE WHEN bytes_rank <= %(top_bytes)s THEN 'top_bytes' END
                   ], NULL) AS criteria
            FROM origin_stats
        )
    """


def _criteria_params() -> dict[str, int]:
    return {
        "min_destinations": MIN_DESTINATIONS_EXCLUSIVE,
        "min_ports": MIN_PORTS_PER_DESTINATION_EXCLUSIVE,
        "top_bytes": TOP_BYTES_LIMIT,
    }


def _sort_clause(sort: OriginSort, order: SortOrder) -> str:
    # `sort` e `order` vêm de Literals validados pela rota, nunca de texto livre.
    direction = "ASC" if order == "asc" else "DESC"
    nulls = "NULLS LAST"
    return f"{sort} {direction} {nulls}, src_ip ASC"


def list_flagged(
    conn: Conn,
    time_range: TimeRange,
    criteria: list[Criterion] | None,
    sort: OriginSort,
    order: SortOrder,
    limit: int,
    offset: int,
) -> tuple[int, list[dict[str, Any]]]:
    """Página de origens que acionaram ao menos um critério (ou algum dos pedidos)."""
    params: dict[str, Any] = {
        **time_range.params(),
        **_criteria_params(),
        "filter": list(criteria) if criteria else None,
        "limit": limit,
        "offset": offset,
    }
    base = (
        _origin_stats_sql()
        + """
        , flagged AS (
            SELECT * FROM with_criteria
            WHERE cardinality(criteria) > 0
              AND (%(filter)s::text[] IS NULL OR criteria && %(filter)s::text[])
        )
    """
    )
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(base + "SELECT count(*) AS total FROM flagged", params)
        total_row = cur.fetchone()
        assert total_row is not None
        cur.execute(
            base
            + f"""
            SELECT * FROM flagged
            ORDER BY {_sort_clause(sort, order)}
            LIMIT %(limit)s OFFSET %(offset)s
            """,
            params,
        )
        return int(total_row["total"]), cur.fetchall()


def criteria_counts(conn: Conn, time_range: TimeRange) -> dict[str, int]:
    """Quantas origens acionaram cada critério no período (para os filtros da tela)."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            _origin_stats_sql()
            + """
            SELECT
                count(*) FILTER (WHERE cardinality(criteria) > 0)            AS any,
                count(*) FILTER (WHERE 'indicator' = ANY(criteria))          AS indicator,
                count(*) FILTER (WHERE 'many_destinations' = ANY(criteria))  AS many_destinations,
                count(*) FILTER (WHERE 'many_ports' = ANY(criteria))         AS many_ports,
                count(*) FILTER (WHERE 'top_bytes' = ANY(criteria))          AS top_bytes
            FROM with_criteria
            """,
            {**time_range.params(), **_criteria_params()},
        )
        row = cur.fetchone()
    assert row is not None
    return {key: int(value) for key, value in row.items()}


def get_origin(conn: Conn, ip: IPv4Address) -> dict[str, Any] | None:
    """Identificação da origem e dados do indicador, independentemente do período."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT o.ip, o.asn, o.country,
                   i.category, i.source, i.confidence,
                   i.first_seen AS indicator_first_seen,
                   i.last_seen  AS indicator_last_seen
            FROM origins o
            LEFT JOIN indicators i ON i.ip = o.ip
            WHERE o.ip = %(ip)s
            """,
            {"ip": ip},
        )
        return cur.fetchone()


def origin_stats(conn: Conn, time_range: TimeRange, ip: IPv4Address) -> dict[str, Any] | None:
    """Estatísticas e critérios da origem no período; None se ela não teve tráfego."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            _origin_stats_sql() + "SELECT * FROM with_criteria WHERE src_ip = %(ip)s",
            {**time_range.params(), **_criteria_params(), "ip": ip},
        )
        return cur.fetchone()


def destinations(
    conn: Conn, time_range: TimeRange, ip: IPv4Address, limit: int, offset: int
) -> tuple[int, list[dict[str, Any]]]:
    params = {**time_range.params(), "ip": ip, "limit": limit, "offset": offset}
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT count(DISTINCT dst_ip) AS total
            FROM flows
            WHERE src_ip = %(ip)s AND ts >= %(start)s AND ts < %(end)s
            """,
            params,
        )
        total_row = cur.fetchone()
        assert total_row is not None
        cur.execute(
            """
            SELECT dst_ip,
                   sum(bytes)::bigint                                   AS bytes,
                   sum(packets)::bigint                                 AS packets,
                   count(*)                                             AS flows,
                   count(DISTINCT dst_port) FILTER (WHERE protocol <> 'ICMP') AS ports,
                   min(ts)                                              AS first_seen,
                   max(ts)                                              AS last_seen
            FROM flows
            WHERE src_ip = %(ip)s AND ts >= %(start)s AND ts < %(end)s
            GROUP BY dst_ip
            ORDER BY bytes DESC, dst_ip
            LIMIT %(limit)s OFFSET %(offset)s
            """,
            params,
        )
        return int(total_row["total"]), cur.fetchall()


def ports(
    conn: Conn, time_range: TimeRange, ip: IPv4Address, limit: int, offset: int
) -> tuple[int, list[dict[str, Any]]]:
    # Porta e protocolo juntos identificam o serviço: 53/UDP e 53/TCP são coisas diferentes.
    params = {**time_range.params(), "ip": ip, "limit": limit, "offset": offset}
    where = """
        WHERE src_ip = %(ip)s AND ts >= %(start)s AND ts < %(end)s AND protocol <> 'ICMP'
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"SELECT count(*) AS total FROM (SELECT 1 FROM flows {where} "
            "GROUP BY dst_port, protocol) AS services",
            params,
        )
        total_row = cur.fetchone()
        assert total_row is not None
        cur.execute(
            f"""
            SELECT dst_port AS port, protocol,
                   count(*)               AS flows,
                   sum(bytes)::bigint     AS bytes,
                   sum(packets)::bigint   AS packets,
                   count(DISTINCT dst_ip) AS destinations
            FROM flows
            {where}
            GROUP BY dst_port, protocol
            ORDER BY flows DESC, port, protocol
            LIMIT %(limit)s OFFSET %(offset)s
            """,
            params,
        )
        return int(total_row["total"]), cur.fetchall()


def flows(
    conn: Conn,
    time_range: TimeRange,
    ip: IPv4Address,
    sort: FlowSort,
    order: SortOrder,
    limit: int,
    offset: int,
) -> tuple[int, list[dict[str, Any]]]:
    params = {**time_range.params(), "ip": ip, "limit": limit, "offset": offset}
    direction = "ASC" if order == "asc" else "DESC"
    where = "WHERE src_ip = %(ip)s AND ts >= %(start)s AND ts < %(end)s"
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SELECT count(*) AS total FROM flows {where}", params)
        total_row = cur.fetchone()
        assert total_row is not None
        cur.execute(
            f"""
            SELECT id, ts, src_port, dst_ip, dst_port, protocol, bytes, packets
            FROM flows
            {where}
            ORDER BY {sort} {direction}, id {direction}
            LIMIT %(limit)s OFFSET %(offset)s
            """,
            params,
        )
        return int(total_row["total"]), cur.fetchall()
