from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any

import psycopg
from fastapi import Depends, HTTPException, Query, Request
from psycopg_pool import ConnectionPool

from app.repositories.overview import MAX_POINTS, auto_bucket_seconds, bucket_count
from app.repositories.time_range import TimeRange, data_bounds
from app.schemas.common import PeriodOut

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


def period_out(period: TimeRange) -> PeriodOut:
    return PeriodOut(start=period.start, end=period.end)


def resolve_bucket(period: TimeRange, bucket: int | None) -> int:
    """Intervalo pedido ou automático, limitado a MAX_POINTS pontos por série."""
    bucket_seconds = bucket or auto_bucket_seconds(period)
    if bucket_count(period, bucket_seconds) > MAX_POINTS:
        raise HTTPException(
            status_code=422,
            detail=f"Intervalo pequeno demais para o período: máximo de {MAX_POINTS} pontos.",
        )
    return bucket_seconds


@dataclass(frozen=True)
class Pagination:
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def get_pagination(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 25,
) -> Pagination:
    return Pagination(page=page, page_size=page_size)


Paging = Annotated[Pagination, Depends(get_pagination)]
