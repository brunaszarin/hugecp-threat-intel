from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated, Any

import psycopg
from fastapi import Depends, HTTPException, Query, Request
from psycopg_pool import ConnectionPool

from app.repositories.time_range import TimeRange, data_bounds

Conn = psycopg.Connection[Any]


def get_conn(request: Request) -> Iterator[Conn]:
    pool: ConnectionPool = request.app.state.pool
    with pool.connection() as conn:
        yield conn


DbConn = Annotated[Conn, Depends(get_conn)]


def _as_utc(value: datetime) -> datetime:
    # Datas sem fuso são interpretadas como UTC, o mesmo fuso dos timestamps do CSV.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def get_time_range(
    conn: DbConn,
    start: Annotated[
        datetime | None,
        Query(alias="from", description="Início do período (inclusivo), ISO 8601."),
    ] = None,
    end: Annotated[
        datetime | None,
        Query(alias="to", description="Fim do período (exclusivo), ISO 8601."),
    ] = None,
) -> TimeRange:
    """Resolve o período pedido. Limites ausentes assumem os limites dos dados."""
    if start is None or end is None:
        bounds = data_bounds(conn)
        start = start or bounds.start
        end = end or bounds.end
    time_range = TimeRange(start=_as_utc(start), end=_as_utc(end))
    if time_range.start >= time_range.end:
        raise HTTPException(status_code=422, detail="'from' precisa ser anterior a 'to'.")
    return time_range


Period = Annotated[TimeRange, Depends(get_time_range)]
