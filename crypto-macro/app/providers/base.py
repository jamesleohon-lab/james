"""Provider interfaces, so data sources can be swapped without touching the
rest of the app (e.g. a paid calendar that supplies actual values)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

IMPACT_LEVELS = {"holiday": 0, "low": 1, "medium": 2, "high": 3}


@dataclass
class CalendarEvent:
    id: str               # stable across fetches (see forexfactory.make_event_ids)
    country: str          # currency code as the provider shows it, e.g. "USD"
    title: str
    impact: str           # "high" | "medium" | "low" | "holiday"
    starts_at: datetime   # timezone-aware, UTC
    all_day: bool = False
    forecast: str | None = None
    previous: str | None = None
    actual: str | None = None


class CalendarProvider(Protocol):
    name: str

    async def fetch_raw(self) -> str:
        """Download the provider's payload (callers handle caching/limits)."""

    def parse(self, raw: str) -> list[CalendarEvent]:
        """Turn a payload into events. Pure, so it can be tested offline."""


class ActualsProvider(Protocol):
    """Supplies released values for events the calendar feed lacks (phase 2:
    BLS/BEA for US data). Returns None until the value is published."""

    name: str

    def handles(self, event: CalendarEvent) -> bool: ...

    async def fetch_actual(self, event: CalendarEvent) -> str | None: ...
