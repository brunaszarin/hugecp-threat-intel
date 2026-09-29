from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class TimeRange:
    """Intervalo semiaberto [start, end)."""

    start: datetime
    end: datetime

    @property
    def seconds(self) -> float:
        return (self.end - self.start).total_seconds()

    def params(self) -> dict[str, datetime]:
        return {"start": self.start, "end": self.end}


def data_bounds(conn: psycopg.Connection[Any]) -> TimeRange:
    """Período coberto pelos dados. O fim é exclusivo, então soma 1s ao último flow."""
    row = conn.execute("SELECT min(ts), max(ts) FROM flows").fetchone()
    if row is None or row[0] is None:
        return TimeRange(start=EPOCH, end=EPOCH + timedelta(seconds=1))
    return TimeRange(start=row[0], end=row[1] + timedelta(seconds=1))
