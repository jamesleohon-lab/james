"""Fetching and caching the calendar feed, respecting its rate limit."""

import logging
from datetime import timedelta

from .db import Database
from .providers.base import CalendarProvider
from .timeutil import to_utc_iso, utcnow

log = logging.getLogger(__name__)


async def refresh_calendar(db: Database, provider: CalendarProvider,
                           min_interval: timedelta) -> dict:
    """Fetch the feed unless we tried too recently.

    The floor applies to failed attempts too, so a rate-limit response never
    turns into a retry loop. On any failure the previously stored events are
    left untouched.
    """
    last = db.last_attempt_at(provider.name)
    now = utcnow()
    if last and now - last < min_interval:
        return {"ok": False, "skipped": True,
                "next_allowed_at": to_utc_iso(last + min_interval)}

    try:
        raw = await provider.fetch_raw()
        events = provider.parse(raw)
        if not events:
            raise ValueError("feed contained no events")
    except Exception as exc:  # network, HTTP status, bad payload
        log.warning("calendar fetch failed: %s", exc)
        db.record_fetch(provider.name, ok=False, error=str(exc)[:500])
        return {"ok": False, "skipped": False, "error": str(exc)}

    db.save_cache(provider.name, raw)
    counts = db.sync_events(provider.name, events)
    db.record_fetch(provider.name, ok=True, n_events=len(events))
    log.info("calendar refreshed: %d events %s", len(events), counts)
    return {"ok": True, "n_events": len(events), **counts}


def restore_from_cache(db: Database, provider: CalendarProvider) -> int:
    """Re-parse the last good payload (e.g. after a parser change) without
    touching the network."""
    raw = db.load_cache(provider.name)
    if not raw:
        return 0
    try:
        events = provider.parse(raw)
    except Exception as exc:
        log.warning("cached feed could not be parsed: %s", exc)
        return 0
    db.sync_events(provider.name, events)
    return len(events)
