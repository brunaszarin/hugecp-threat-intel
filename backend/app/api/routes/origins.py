from ipaddress import IPv4Address
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import DbConn, Paging, Period, period_out, resolve_bucket
from app.repositories import origins as repo
from app.repositories import overview as overview_repo
from app.schemas.common import Page
from app.schemas.origins import (
    CriteriaCounts,
    DestinationStat,
    FlowItem,
    IndicatorInfo,
    OriginDetail,
    OriginList,
    OriginListItem,
    OriginStats,
    PortServiceStat,
)
from app.schemas.overview import Timeseries, TimeseriesPoint

router = APIRouter(prefix="/origins", tags=["origins"])


def _indicator(row: dict[str, Any]) -> IndicatorInfo | None:
    if row["category"] is None:
        return None
    return IndicatorInfo(
        category=row["category"],
        source=row["source"],
        confidence=row["confidence"],
        first_seen=row["indicator_first_seen"],
        last_seen=row["indicator_last_seen"],
    )


@router.get("", response_model_by_alias=True)
def list_origins(
    conn: DbConn,
    period: Period,
    paging: Paging,
    criteria: Annotated[
        list[repo.Criterion] | None,
        Query(description="Mostra só origens que acionaram algum destes critérios."),
    ] = None,
    sort: repo.OriginSort = "bytes",
    order: repo.SortOrder = "desc",
) -> OriginList:
    """Origens que merecem atenção: acionaram pelo menos um dos critérios no período."""
    total, rows = repo.list_flagged(
        conn, period, criteria, sort, order, paging.page_size, paging.offset
    )
    return OriginList(
        period=period_out(period),
        total=total,
        page=paging.page,
        page_size=paging.page_size,
        criteria_counts=CriteriaCounts(**repo.criteria_counts(conn, period)),
        items=[OriginListItem(**row, ip=row["src_ip"], indicator=_indicator(row)) for row in rows],
    )


def _require_origin(conn: DbConn, ip: IPv4Address) -> dict[str, Any]:
    origin = repo.get_origin(conn, ip)
    if origin is None:
        raise HTTPException(status_code=404, detail=f"Origem {ip} não encontrada nos dados.")
    return origin


@router.get("/{ip}", response_model_by_alias=True)
def get_origin(conn: DbConn, period: Period, ip: IPv4Address) -> OriginDetail:
    """Identificação, dados do indicador, estatísticas e critérios acionados no período."""
    origin = _require_origin(conn, ip)
    stats = repo.origin_stats(conn, period, ip)
    return OriginDetail(
        period=period_out(period),
        ip=origin["ip"],
        asn=origin["asn"],
        country=origin["country"],
        indicator=_indicator(origin),
        stats=OriginStats(**stats) if stats else None,
        criteria=stats["criteria"] if stats else [],
    )


@router.get("/{ip}/timeseries", response_model_by_alias=True)
def get_origin_timeseries(
    conn: DbConn,
    period: Period,
    ip: IPv4Address,
    bucket: Annotated[int | None, Query(ge=1)] = None,
) -> Timeseries:
    """Atividade da origem ao longo do tempo."""
    _require_origin(conn, ip)
    bucket_seconds = resolve_bucket(period, bucket)
    rows = overview_repo.timeseries(conn, period, bucket_seconds, src_ip=ip)
    return Timeseries(
        period=period_out(period),
        bucket_seconds=bucket_seconds,
        points=[TimeseriesPoint(**row) for row in rows],
    )


@router.get("/{ip}/destinations", response_model_by_alias=True)
def get_origin_destinations(
    conn: DbConn, period: Period, paging: Paging, ip: IPv4Address
) -> Page[DestinationStat]:
    """IPs protegidos atingidos pela origem e o tráfego enviado a cada um."""
    _require_origin(conn, ip)
    total, rows = repo.destinations(conn, period, ip, paging.page_size, paging.offset)
    return Page[DestinationStat](
        period=period_out(period),
        total=total,
        page=paging.page,
        page_size=paging.page_size,
        items=[DestinationStat(**row) for row in rows],
    )


@router.get("/{ip}/ports", response_model_by_alias=True)
def get_origin_ports(
    conn: DbConn, period: Period, paging: Paging, ip: IPv4Address
) -> Page[PortServiceStat]:
    """Portas procuradas pela origem (porta + protocolo) e em quantos flows."""
    _require_origin(conn, ip)
    total, rows = repo.ports(conn, period, ip, paging.page_size, paging.offset)
    return Page[PortServiceStat](
        period=period_out(period),
        total=total,
        page=paging.page,
        page_size=paging.page_size,
        items=[PortServiceStat(**row) for row in rows],
    )


@router.get("/{ip}/flows", response_model_by_alias=True)
def get_origin_flows(
    conn: DbConn,
    period: Period,
    paging: Paging,
    ip: IPv4Address,
    sort: repo.FlowSort = "ts",
    order: repo.SortOrder = "asc",
) -> Page[FlowItem]:
    """Flows da origem no período, paginados."""
    _require_origin(conn, ip)
    total, rows = repo.flows(conn, period, ip, sort, order, paging.page_size, paging.offset)
    return Page[FlowItem](
        period=period_out(period),
        total=total,
        page=paging.page,
        page_size=paging.page_size,
        items=[FlowItem(**row) for row in rows],
    )
