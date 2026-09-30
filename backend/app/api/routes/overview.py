from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.api.deps import DbConn, Period, period_out, resolve_bucket
from app.repositories import overview as repo
from app.schemas.overview import (
    IndicatorTraffic,
    OverviewSummary,
    PortStat,
    ProtocolBreakdown,
    ProtocolStat,
    Timeseries,
    TimeseriesPoint,
    TopPorts,
)

router = APIRouter(prefix="/overview", tags=["overview"])


@router.get("/summary", response_model_by_alias=True)
def get_summary(conn: DbConn, period: Period) -> OverviewSummary:
    """Totais do período e o tráfego vindo de origens que estão na lista de indicadores."""
    row = repo.summary(conn, period)
    total = row["bytes"]
    return OverviewSummary(
        period=period_out(period),
        bytes=total,
        packets=row["packets"],
        flows=row["flows"],
        sources=row["sources"],
        destinations=row["destinations"],
        indicators=IndicatorTraffic(
            bytes=row["ind_bytes"],
            packets=row["ind_packets"],
            flows=row["ind_flows"],
            sources=row["ind_sources"],
            bytes_pct=round(100 * row["ind_bytes"] / total, 2) if total else 0.0,
        ),
    )


@router.get("/timeseries", response_model_by_alias=True)
def get_timeseries(
    conn: DbConn,
    period: Period,
    bucket: Annotated[
        int | None,
        Query(ge=1, description="Tamanho do intervalo em segundos. Omitido: automático."),
    ] = None,
) -> Timeseries:
    """Bytes, pacotes e flows por intervalo de tempo, com intervalos vazios preenchidos."""
    bucket_seconds = resolve_bucket(period, bucket)
    rows = repo.timeseries(conn, period, bucket_seconds)
    return Timeseries(
        period=period_out(period),
        bucket_seconds=bucket_seconds,
        points=[TimeseriesPoint(**row) for row in rows],
    )


@router.get("/protocols", response_model_by_alias=True)
def get_protocols(conn: DbConn, period: Period) -> ProtocolBreakdown:
    """Distribuição do tráfego por protocolo."""
    rows = repo.protocols(conn, period)
    return ProtocolBreakdown(period=period_out(period), items=[ProtocolStat(**row) for row in rows])


@router.get("/top-ports", response_model_by_alias=True)
def get_top_ports(
    conn: DbConn,
    period: Period,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    order_by: Literal["flows", "bytes"] = "flows",
) -> TopPorts:
    """Portas de destino mais procuradas (ICMP fica de fora por não ter portas)."""
    rows = repo.top_ports(conn, period, limit, order_by)
    return TopPorts(
        period=period_out(period), order_by=order_by, items=[PortStat(**row) for row in rows]
    )
