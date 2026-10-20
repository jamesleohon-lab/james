"""Timezone helpers. Everything is stored in UTC and shown in Europe/London."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .config import DISPLAY_TZ

LONDON = ZoneInfo(DISPLAY_TZ)
UTC = timezone.utc


def utcnow() -> datetime:
    return datetime.now(UTC)


def parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 timestamp; naive values are treated as UTC."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def to_utc_iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_london(dt: datetime) -> datetime:
    return dt.astimezone(LONDON)


def london_fields(dt: datetime) -> dict:
    """Display fields for the frontend, computed server-side so day grouping
    is right across DST changes regardless of the phone's own timezone."""
    local = to_london(dt)
    return {
        "london_date": local.strftime("%Y-%m-%d"),
        "london_day": local.strftime("%a %d %b").replace(" 0", " "),
        "london_time": local.strftime("%H:%M"),
        "london_tz": local.tzname(),  # GMT or BST
    }
