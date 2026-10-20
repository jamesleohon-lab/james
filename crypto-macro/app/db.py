"""SQLite storage. Plain sqlite3; one connection per call keeps it simple and
safe across the web handlers and the scheduler."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .providers.base import IMPACT_LEVELS, CalendarEvent
from .providers.forexfactory import feed_week
from .timeutil import parse_iso, to_utc_iso, utcnow

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id            TEXT PRIMARY KEY,
    provider      TEXT NOT NULL,
    country       TEXT NOT NULL,
    title         TEXT NOT NULL,
    impact        TEXT NOT NULL,
    starts_at     TEXT NOT NULL,      -- UTC ISO-8601
    all_day       INTEGER NOT NULL DEFAULT 0,
    forecast      TEXT,
    previous      TEXT,
    actual        TEXT,
    feed_week     TEXT NOT NULL,      -- Sunday (US Eastern) of the FF week
    first_seen_at TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_starts_at ON events(starts_at);

CREATE TABLE IF NOT EXISTS feed_fetches (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    provider    TEXT NOT NULL,
    fetched_at  TEXT NOT NULL,
    ok          INTEGER NOT NULL,
    n_events    INTEGER,
    error       TEXT
);

-- Last good raw payload per provider, kept so we can re-parse without
-- hitting the rate-limited feed again.
CREATE TABLE IF NOT EXISTS feed_cache (
    provider    TEXT PRIMARY KEY,
    fetched_at  TEXT NOT NULL,
    body        TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # --- events -----------------------------------------------------------

    def sync_events(self, provider: str, events: list[CalendarEvent]) -> dict:
        """Upsert a full feed snapshot. Events that disappeared from a week
        the feed covers are deleted (cancelled or retitled upstream). An
        actual value we already hold is never overwritten with an empty one."""
        now = to_utc_iso(utcnow())
        weeks = {feed_week(e.starts_at).isoformat() for e in events}
        ids = {e.id for e in events}
        added = updated = removed = 0
        with self.connect() as conn:
            for e in events:
                week = feed_week(e.starts_at).isoformat()
                row = conn.execute("SELECT id FROM events WHERE id = ?", (e.id,)).fetchone()
                values = (e.country, e.title, e.impact, to_utc_iso(e.starts_at),
                          int(e.all_day), e.forecast, e.previous, e.actual, week, now)
                if row:
                    conn.execute(
                        """UPDATE events SET country=?, title=?, impact=?, starts_at=?,
                           all_day=?, forecast=?, previous=?,
                           actual=COALESCE(?, actual), feed_week=?, updated_at=?
                           WHERE id=?""", values + (e.id,))
                    updated += 1
                else:
                    conn.execute(
                        """INSERT INTO events (country, title, impact, starts_at, all_day,
                           forecast, previous, actual, feed_week, updated_at,
                           id, provider, first_seen_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        values + (e.id, provider, now))
                    added += 1
            for week in weeks:
                stale = [r["id"] for r in conn.execute(
                    "SELECT id FROM events WHERE provider=? AND feed_week=?",
                    (provider, week)) if r["id"] not in ids]
                for event_id in stale:
                    conn.execute("DELETE FROM events WHERE id=?", (event_id,))
                removed += len(stale)
        return {"added": added, "updated": updated, "removed": removed}

    def list_events(self, start: datetime, end: datetime,
                    countries: list[str] | None = None,
                    min_impact_rank: int = 0) -> list[dict]:
        allowed = [k for k, v in IMPACT_LEVELS.items() if v >= min_impact_rank]
        sql = ["SELECT * FROM events WHERE starts_at >= ? AND starts_at < ?"]
        params: list = [to_utc_iso(start), to_utc_iso(end)]
        if countries:
            sql.append(f"AND country IN ({','.join('?' * len(countries))})")
            params += countries
        sql.append(f"AND impact IN ({','.join('?' * len(allowed))})")
        params += allowed
        sql.append("ORDER BY starts_at, country, title")
        with self.connect() as conn:
            return [dict(r) for r in conn.execute(" ".join(sql), params)]

    def countries(self) -> list[str]:
        with self.connect() as conn:
            return [r[0] for r in conn.execute(
                "SELECT DISTINCT country FROM events ORDER BY country")]

    # --- feed bookkeeping -------------------------------------------------

    def record_fetch(self, provider: str, ok: bool, n_events: int | None = None,
                     error: str | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO feed_fetches (provider, fetched_at, ok, n_events, error) "
                "VALUES (?,?,?,?,?)",
                (provider, to_utc_iso(utcnow()), int(ok), n_events, error))

    def last_fetch(self, provider: str, ok_only: bool = False) -> dict | None:
        sql = "SELECT * FROM feed_fetches WHERE provider=?"
        if ok_only:
            sql += " AND ok=1"
        with self.connect() as conn:
            row = conn.execute(sql + " ORDER BY id DESC LIMIT 1", (provider,)).fetchone()
        return dict(row) if row else None

    def last_attempt_at(self, provider: str) -> datetime | None:
        row = self.last_fetch(provider)
        return parse_iso(row["fetched_at"]) if row else None

    def save_cache(self, provider: str, body: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO feed_cache (provider, fetched_at, body) VALUES (?,?,?) "
                "ON CONFLICT(provider) DO UPDATE SET fetched_at=excluded.fetched_at, "
                "body=excluded.body",
                (provider, to_utc_iso(utcnow()), body))

    def load_cache(self, provider: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute("SELECT body FROM feed_cache WHERE provider=?",
                               (provider,)).fetchone()
        return row["body"] if row else None

