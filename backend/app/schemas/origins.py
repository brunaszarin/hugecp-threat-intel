from datetime import datetime
from ipaddress import IPv4Address
from typing import Literal

from pydantic import BaseModel, Field

from app.repositories.origins import Criterion
from app.schemas.common import Page, PeriodOut


class IndicatorInfo(BaseModel):
    category: Literal["scan", "botnet", "c2", "tor_exit"]
    source: str
    confidence: int = Field(ge=0, le=100)
    first_seen: datetime
    last_seen: datetime


class OriginStats(BaseModel):
    bytes: int
    packets: int
    flows: int
    destinations: int
    ports: int = Field(description="Portas de destino distintas (ICMP não conta).")
    max_ports_per_destination: int
    first_seen: datetime
    last_seen: datetime


class OriginListItem(OriginStats):
    ip: IPv4Address
    asn: int
    country: str
    indicator: IndicatorInfo | None
    criteria: list[Criterion]


class CriteriaCounts(BaseModel):
    any: int
    indicator: int
    many_destinations: int
    many_ports: int
    top_bytes: int


class OriginList(Page[OriginListItem]):
    criteria_counts: CriteriaCounts = Field(
        description="Origens por critério no período, independente do filtro aplicado."
    )


class OriginDetail(BaseModel):
    period: PeriodOut
    ip: IPv4Address
    asn: int
    country: str
    indicator: IndicatorInfo | None
    stats: OriginStats | None = Field(description="Nulo se a origem não teve tráfego no período.")
    criteria: list[Criterion]


class DestinationStat(BaseModel):
    dst_ip: IPv4Address
    bytes: int
    packets: int
    flows: int
    ports: int
    first_seen: datetime
    last_seen: datetime


class PortServiceStat(BaseModel):
    port: int
    protocol: Literal["TCP", "UDP"]
    flows: int
    bytes: int
    packets: int
    destinations: int


class FlowItem(BaseModel):
    id: int
    ts: datetime
    src_port: int
    dst_ip: IPv4Address
    dst_port: int
    protocol: Literal["TCP", "UDP", "ICMP"]
    bytes: int
    packets: int
