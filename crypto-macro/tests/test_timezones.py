"""US and UK change clocks on different dates, so the gap between New York
and London is 4h for a few weeks a year. These cover those windows."""

import pytest

from app.providers.forexfactory import parse_feed
from app.timeutil import london_fields


@pytest.fixture
def by_date(fixture_text):
    events = parse_feed(fixture_text("ff_dst_mismatch.json"))
    return {london_fields(e.starts_at)["london_date"] + " " + e.country: london_fields(e.starts_at)
            for e in events}


@pytest.mark.parametrize("key,time,tz", [
    ("2026-10-20 USD", "13:30", "BST"),   # both on summer time: 5h gap
    ("2026-10-27 USD", "12:30", "GMT"),   # UK back on GMT, US still EDT: 4h gap
    ("2026-11-03 USD", "13:30", "GMT"),   # both on winter time: 5h gap
    ("2026-03-10 USD", "12:30", "GMT"),   # US on EDT from 8 Mar, UK not until 29 Mar
])
def test_us_release_in_london_time(by_date, key, time, tz):
    assert by_date[key]["london_time"] == time
    assert by_date[key]["london_tz"] == tz


def test_evening_us_time_rolls_to_next_london_day(by_date):
    # 23:30 ET Monday 26 Oct is 03:30 Tuesday in London
    assert by_date["2026-10-27 AUD"]["london_time"] == "03:30"
    assert by_date["2026-10-27 AUD"]["london_day"] == "Tue 27 Oct"
