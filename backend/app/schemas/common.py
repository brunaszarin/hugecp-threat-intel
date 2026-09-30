from datetime import datetime

from pydantic import BaseModel, Field


class PeriodOut(BaseModel):
    start: datetime = Field(serialization_alias="from")
    end: datetime = Field(serialization_alias="to")


class Page[T](BaseModel):
    period: PeriodOut
    total: int = Field(description="Total de itens em todas as páginas.")
    page: int
    page_size: int
    items: list[T]
