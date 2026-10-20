import json
from datetime import date, datetime, timezone

import pytest

from app.providers.forexfactory import FeedError, feed_week, parse_feed
from app.timeutil import london_fields


def test_parses_all_rows(ff_raw):
    events = parse_feed(ff_raw)
    assert len(events) == 13
    cpi = next(e for e in events if e.title == "CPI m/m")
    assert cpi.country == "USD"
    assert cpi.impact == "high"
    assert cpi.forecast == "0.3%" and cpi.previous == "0.4%"
    assert cpi.actual is None
    # 08:30 US Eastern (EDT, -04:00) is 12:30 UTC
    assert cpi.starts_at == datetime(2026, 10, 23, 12, 30, tzinfo=timezone.utc)


def test_empty_strings_become_none_and_holidays_are_all_day(ff_raw):
    events = parse_feed(ff_raw)
    minutes = next(e for e in events if e.title == "Monetary Policy Meeting Minutes")
    assert minutes.forecast is None and minutes.previous is None
    holiday = next(e for e in events if e.impact == "holiday")
    assert holiday.all_day


def test_ids_are_stable_and_unique_for_repeated_titles(ff_raw):
    first = parse_feed(ff_raw)
    second = parse_feed(ff_raw)
    assert [e.id for e in first] == [e.id for e in second]
    assert len({e.id for e in first}) == len(first)
    waller = [e for e in first if "Waller" in e.title]
    assert len(waller) == 2 and waller[0].id != waller[1].id


def test_id_survives_value_and_time_changes(ff_raw):
    rows = json.loads(ff_raw)
    original = {e.title: e.id for e in parse_feed(ff_raw)}
    for r in rows:
        if r["title"] == "Unemployment Claims":
            r["date"] = "2026-10-22T09:00:00-04:00"  # rescheduled same week
            r["forecast"] = "240K"
    changed = {e.title: e.id for e in parse_feed(json.dumps(rows))}
    assert changed["Unemployment Claims"] == original["Unemployment Claims"]


def test_bad_rows_are_skipped():
    raw = json.dumps([
        {"title": "No date", "country": "USD"},
        {"title": "Bad date", "country": "USD", "date": "soon"},
        "not a dict",
        {"title": "Odd impact", "country": "usd", "date": "2026-10-20T08:30:00-04:00",
         "impact": "Non-Economic"},
    ])
    events = parse_feed(raw)
    assert len(events) == 1
    assert events[0].country == "USD" and events[0].impact == "low"


@pytest.mark.parametrize("raw", ["<html>Request Denied</html>", '{"error": 1}'])
def test_non_list_payload_raises(raw):
    with pytest.raises(FeedError):
        parse_feed(raw)


def test_feed_week_is_us_eastern_sunday():
    # Saturday 23:30 ET is still the week that began the previous Sunday,
    # even though it's already Sunday in UTC and London.
    sat_night = datetime(2026, 10, 25, 3, 30, tzinfo=timezone.utc)
    assert feed_week(sat_night) == date(2026, 10, 18)
    assert feed_week(datetime(2026, 10, 25, 5, 0, tzinfo=timezone.utc)) == date(2026, 10, 25)


def test_london_fields_shape():
    f = london_fields(datetime(2026, 10, 23, 12, 30, tzinfo=timezone.utc))
    assert f == {"london_date": "2026-10-23", "london_day": "Fri 23 Oct",
                 "london_time": "13:30", "london_tz": "BST"}
