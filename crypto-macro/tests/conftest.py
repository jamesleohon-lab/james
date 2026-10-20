from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.config import Settings
from app.db import Database
from app.providers.forexfactory import parse_feed

FIXTURES = Path(__file__).parent / "fixtures"

# Tuesday 20 Oct 2026, 14:00 UTC (15:00 BST), mid-way through the fixture week
FROZEN_NOW = datetime(2026, 10, 20, 14, 0, tzinfo=timezone.utc)


@pytest.fixture
def fixture_text():
    return lambda name: (FIXTURES / name).read_text()


@pytest.fixture
def ff_raw(fixture_text):
    return fixture_text("ff_thisweek.json")


class FakeProvider:
    name = "forexfactory"

    def __init__(self, raw: str | None = None, error: Exception | None = None):
        self.raw, self.error, self.calls = raw, error, 0

    async def fetch_raw(self) -> str:
        self.calls += 1
        if self.error:
            raise self.error
        return self.raw

    def parse(self, raw: str):
        return parse_feed(raw)


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def make_settings(tmp_path):
    def make(**overrides):
        s = Settings(database_path=str(tmp_path / "app.db"), scheduler_enabled=False,
                     app_passcode="", secret_key="test")
        for k, v in overrides.items():
            setattr(s, k, v)
        return s
    return make


@pytest.fixture
def frozen_now(monkeypatch):
    for module in ("app.api.routes", "app.calendar_service", "app.db"):
        monkeypatch.setattr(f"{module}.utcnow", lambda: FROZEN_NOW)
    return FROZEN_NOW
