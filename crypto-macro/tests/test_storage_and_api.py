import asyncio
import json
from datetime import timedelta

from fastapi.testclient import TestClient

from app.calendar_service import refresh_calendar
from app.main import create_app
from app.providers.forexfactory import parse_feed

from .conftest import FakeProvider

HOUR = timedelta(hours=1)


def test_sync_upserts_and_removes_dropped_events(db, ff_raw):
    first = db.sync_events("forexfactory", parse_feed(ff_raw))
    assert first == {"added": 13, "updated": 0, "removed": 0}

    rows = [r for r in json.loads(ff_raw) if r["title"] != "Crude Oil Inventories"]
    second = db.sync_events("forexfactory", parse_feed(json.dumps(rows)))
    assert second == {"added": 0, "updated": 12, "removed": 1}


def test_sync_keeps_known_actual(db, ff_raw):
    rows = json.loads(ff_raw)
    for r in rows:
        if r["title"] == "Unemployment Claims":
            r["actual"] = "225K"
    db.sync_events("forexfactory", parse_feed(json.dumps(rows)))
    db.sync_events("forexfactory", parse_feed(ff_raw))  # feed without actuals
    with db.connect() as conn:
        actual = conn.execute(
            "SELECT actual FROM events WHERE title='Unemployment Claims'").fetchone()[0]
    assert actual == "225K"


def test_refresh_respects_rate_limit_floor(db, ff_raw, frozen_now):
    provider = FakeProvider(ff_raw)
    assert asyncio.run(refresh_calendar(db, provider, HOUR))["ok"]
    again = asyncio.run(refresh_calendar(db, provider, HOUR))
    assert again["skipped"] and provider.calls == 1


def test_failed_fetch_keeps_existing_events_and_counts_toward_floor(db, ff_raw, monkeypatch):
    db.sync_events("forexfactory", parse_feed(ff_raw))
    provider = FakeProvider(error=RuntimeError("HTTP 429 from feed"))
    result = asyncio.run(refresh_calendar(db, provider, HOUR))
    assert not result["ok"] and "429" in result["error"]
    assert len(db.countries()) > 1
    assert asyncio.run(refresh_calendar(db, provider, HOUR))["skipped"]


def _client(make_settings, ff_raw, **settings):
    app = create_app(make_settings(**settings), provider=FakeProvider(ff_raw))
    app.state.db.sync_events("forexfactory", parse_feed(ff_raw))
    return TestClient(app)


def test_events_default_filters_usd_high(make_settings, ff_raw, frozen_now):
    with _client(make_settings, ff_raw) as client:
        data = client.get("/api/events").json()
    titles = [e["title"] for e in data["events"]]
    assert titles == ["Unemployment Claims", "CPI m/m", "Core CPI m/m"]
    assert data["next_event"]["title"] == "Unemployment Claims"
    claims = data["events"][0]
    assert claims["london_time"] == "13:30" and claims["london_day"] == "Thu 22 Oct"


def test_events_filters_and_past_flag(make_settings, ff_raw, frozen_now):
    with _client(make_settings, ff_raw) as client:
        data = client.get("/api/events?currencies=USD,GBP&min_impact=medium").json()
    by_title = {e["title"]: e for e in data["events"]}
    assert "CPI y/y" in by_title and "Crude Oil Inventories" not in by_title
    waller = [e for e in data["events"] if "Waller" in e["title"]]
    assert [e["is_past"] for e in waller] == [True, False]


def test_events_rejects_bad_impact(make_settings, ff_raw, frozen_now):
    with _client(make_settings, ff_raw) as client:
        assert client.get("/api/events?min_impact=huge").status_code == 400


def test_passcode_login(make_settings, ff_raw, frozen_now):
    with _client(make_settings, ff_raw, app_passcode="hunter2") as client:
        assert client.get("/api/events").status_code == 401
        assert client.get("/api/auth").json() == {"required": True, "authenticated": False}
        assert client.post("/api/login", json={"passcode": "nope"}).status_code == 401
        assert client.post("/api/login", json={"passcode": "hunter2"}).status_code == 200
        assert client.get("/api/events").status_code == 200
        assert client.get("/").status_code == 200  # app shell is always public
