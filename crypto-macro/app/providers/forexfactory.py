"""Forex Factory weekly feed (nfs.faireconomy.media).

The JSON looks like:
    [{"title": "CPI m/m", "country": "USD", "date": "2026-10-15T08:30:00-04:00",
      "impact": "High", "forecast": "0.3%", "previous": "0.4%"}, ...]

Dates carry a US Eastern offset (-04:00 / -05:00), which we convert to UTC.
The feed has no stable event id and no actual values.
"""

import hashlib
import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from ..timeutil import parse_iso
from .base import IMPACT_LEVELS, CalendarEvent

NEW_YORK = ZoneInfo("America/New_York")


class FeedError(Exception):
    pass


def feed_week(dt: datetime) -> date:
    """Sunday that starts the Forex Factory week (US Eastern) containing dt."""
    et = dt.astimezone(NEW_YORK).date()
    return et - timedelta(days=(et.weekday() + 1) % 7)


def _clean(value) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _event_id(country: str, title: str, week: date, ordinal: int) -> str:
    key = f"ff|{country}|{title.lower()}|{week.isoformat()}|{ordinal}"
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def parse_feed(raw: str) -> list[CalendarEvent]:
    try:
        rows = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FeedError(f"feed is not valid JSON: {exc}") from exc
    if not isinstance(rows, list):
        raise FeedError("feed JSON is not a list")

    parsed = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = _clean(row.get("title"))
        country = _clean(row.get("country"))
        when = _clean(row.get("date"))
        if not (title and country and when):
            continue
        try:
            starts_at = parse_iso(when)
        except ValueError:
            continue
        impact = (_clean(row.get("impact")) or "low").lower()
        if impact not in IMPACT_LEVELS:
            impact = "low"
        parsed.append(dict(
            country=country.upper(),
            title=title,
            impact=impact,
            starts_at=starts_at,
            # Bank holidays are listed at local midnight with no real time.
            all_day=impact == "holiday",
            forecast=_clean(row.get("forecast")),
            previous=_clean(row.get("previous")),
            actual=_clean(row.get("actual")),
        ))

    # The same title can appear several times a week (e.g. "FOMC Member
    # Speaks"), so ids include the occurrence number within the week.
    parsed.sort(key=lambda e: (e["starts_at"], e["country"], e["title"]))
    seen: dict[tuple, int] = defaultdict(int)
    events = []
    for e in parsed:
        group = (e["country"], e["title"].lower(), feed_week(e["starts_at"]))
        ordinal = seen[group]
        seen[group] += 1
        events.append(CalendarEvent(id=_event_id(*group, ordinal), **e))
    return events


class ForexFactoryProvider:
    name = "forexfactory"

    def __init__(self, url: str, timeout: float = 20.0):
        self.url = url
        self.timeout = timeout

    async def fetch_raw(self) -> str:
        headers = {"User-Agent": "crypto-macro/1.0 (personal calendar; cached)"}
        async with httpx.AsyncClient(timeout=self.timeout, headers=headers) as client:
            resp = await client.get(self.url)
        if resp.status_code != 200:
            raise FeedError(f"HTTP {resp.status_code} from feed")
        return resp.text

    def parse(self, raw: str) -> list[CalendarEvent]:
        return parse_feed(raw)

