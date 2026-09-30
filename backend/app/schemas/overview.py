from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import PeriodOut


class IndicatorTraffic(BaseModel):
    bytes: int
    packets: int
    flows: int
    sources: int = Field(description="Origens distintas que estão na lista de indicadores.")
    bytes_pct: float = Field(description="Percentual dos bytes totais (0 a 100).")


class OverviewSummary(BaseModel):
    period: PeriodOut
    bytes: int
    packets: int
    flows: int
    sources: int
    destinations: int
    indicators: IndicatorTraffic


class TimeseriesPoint(BaseModel):
    ts: datetime
    bytes: int
    packets: int
    flows: int


class Timeseries(BaseModel):
    period: PeriodOut
    bucket_seconds: int
    points: list[TimeseriesPoint]


Protocol = Literal["TCP", "UDP", "ICMP"]


class ProtocolStat(BaseModel):
    protocol: Protocol
    bytes: int
    packets: int
    flows: int


class ProtocolBreakdown(BaseModel):
    period: PeriodOut
    items: list[ProtocolStat]


class PortStat(BaseModel):
    port: int
    flows: int
    bytes: int
    packets: int
    sources: int = Field(description="Origens distintas que procuraram a porta.")


class TopPorts(BaseModel):
    period: PeriodOut
    order_by: Literal["flows", "bytes"]
    items: list[PortStat]
