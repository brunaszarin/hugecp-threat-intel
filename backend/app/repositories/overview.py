"""Consultas do panorama. Toda agregação acontece no banco."""

import math
from ipaddress import IPv4Address
from typing import Any, Literal

import psycopg
from psycopg.rows import dict_row

from app.repositories.time_range import TimeRange

Conn = psycopg.Connection[Any]

# Intervalos "redondos" que o analista lê com facilidade no eixo do gráfico.
NICE_BUCKETS = (
    1, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 21600, 43200, 86400,
)  # fmt: skip
TARGET_MAX_POINTS = 200
MAX_POINTS = 5000


def auto_bucket_seconds(time_range: TimeRange) -> int:
    """Menor intervalo redondo que mantém a série com no máximo ~200 pontos."""
    for bucket in NICE_BUCKETS:
        if time_range.seconds / bucket <= TARGET_MAX_POINTS:
            return bucket
    return math.ceil(time_range.seconds / TARGET_MAX_POINTS)


def bucket_count(time_range: TimeRange, bucket_seconds: int) -> int:
    return math.ceil(time_range.seconds / bucket_seconds)


def summary(conn: Conn, time_range: TimeRange) -> dict[str, Any]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT
                coalesce(sum(f.bytes), 0)::bigint                     AS bytes,
                coalesce(sum(f.packets), 0)::bigint                   AS packets,
                count(*)                                              AS flows,
                count(DISTINCT f.src_ip)                              AS sources,
                count(DISTINCT f.dst_ip)                              AS destinations,
                coalesce(sum(f.bytes) FILTER (WHERE i.ip IS NOT NULL), 0)::bigint
                                                                      AS ind_bytes,
                coalesce(sum(f.packets) FILTER (WHERE i.ip IS NOT NULL), 0)::bigint
                                                                      AS ind_packets,
                count(*) FILTER (WHERE i.ip IS NOT NULL)              AS ind_flows,
                count(DISTINCT f.src_ip) FILTER (WHERE i.ip IS NOT NULL)
                                                                      AS ind_sources
            FROM flows f
            LEFT JOIN indicators i ON i.ip = f.src_ip
            WHERE f.ts >= %(start)s AND f.ts < %(end)s
            """,
            time_range.params(),
        )
        row = cur.fetchone()
    assert row is not None
    return row


def timeseries(
    conn: Conn, time_range: TimeRange, bucket_seconds: int, src_ip: IPv4Address | None = None
) -> list[dict[str, Any]]:
    """Série do período inteiro ou, com `src_ip`, de uma única origem."""
    # O filtro é um trecho fixo de SQL; o valor do IP vai sempre como parâmetro.
    src_filter = "AND src_ip = %(src_ip)s" if src_ip is not None else ""
    # Gera todos os intervalos do período e faz LEFT JOIN com os agregados, para que
    # intervalos sem tráfego apareçam como zero em vez de sumirem do gráfico.
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""
            WITH buckets AS (
                SELECT %(start)s::timestamptz + make_interval(secs => i * %(step)s) AS ts
                FROM generate_series(0, %(n)s - 1) AS i
            ),
            agg AS (
                SELECT date_bin(make_interval(secs => %(step)s), ts, %(start)s::timestamptz)
                           AS ts,
                       sum(bytes)::bigint   AS bytes,
                       sum(packets)::bigint AS packets,
                       count(*)             AS flows
                FROM flows
                WHERE ts >= %(start)s AND ts < %(end)s {src_filter}
                GROUP BY 1
            )
            SELECT b.ts,
                   coalesce(a.bytes, 0)   AS bytes,
                   coalesce(a.packets, 0) AS packets,
                   coalesce(a.flows, 0)   AS flows
            FROM buckets b
            LEFT JOIN agg a USING (ts)
            ORDER BY b.ts
            """,
            {
                **time_range.params(),
                "step": bucket_seconds,
                "n": bucket_count(time_range, bucket_seconds),
                "src_ip": src_ip,
            },
        )
        return cur.fetchall()


def protocols(conn: Conn, time_range: TimeRange) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT protocol,
                   sum(bytes)::bigint   AS bytes,
                   sum(packets)::bigint AS packets,
                   count(*)             AS flows
            FROM flows
            WHERE ts >= %(start)s AND ts < %(end)s
            GROUP BY protocol
            ORDER BY bytes DESC
            """,
            time_range.params(),
        )
        return cur.fetchall()


def top_ports(
    conn: Conn, time_range: TimeRange, limit: int, order_by: Literal["flows", "bytes"]
) -> list[dict[str, Any]]:
    # ICMP não tem portas (vem com dst_port = 0); incluí-lo faria a "porta 0"
    # aparecer como se fosse um serviço procurado.
    # `order` vem de um Literal validado pela rota, nunca de texto livre do usuário.
    order = "flows DESC, bytes DESC" if order_by == "flows" else "bytes DESC, flows DESC"
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""
            SELECT dst_port                 AS port,
                   count(*)                 AS flows,
                   sum(bytes)::bigint       AS bytes,
                   sum(packets)::bigint     AS packets,
                   count(DISTINCT src_ip)   AS sources
            FROM flows
            WHERE ts >= %(start)s AND ts < %(end)s
              AND protocol <> 'ICMP'
            GROUP BY dst_port
            ORDER BY {order}, port
            LIMIT %(limit)s
            """,
            {**time_range.params(), "limit": limit},
        )
        return cur.fetchall()
