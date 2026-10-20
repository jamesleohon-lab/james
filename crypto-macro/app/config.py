"""Settings, read once from environment variables (see .env.example)."""

import os
from dataclasses import dataclass, field
from pathlib import Path

DISPLAY_TZ = "Europe/London"

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader so local runs don't need extra tooling.

    Real environment variables always win over the file.
    """
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    database_path: str = field(default_factory=lambda: os.environ.get(
        "DATABASE_PATH", str(BASE_DIR / "data" / "crypto_macro.db")))
    ff_feed_url: str = field(default_factory=lambda: os.environ.get(
        "FF_FEED_URL", "https://nfs.faireconomy.media/ff_calendar_thisweek.json"))
    # How often the scheduler refreshes the feed, and the hard floor between
    # any two fetches (manual refreshes included). The feed is rate-limited.
    feed_refresh_hours: float = field(default_factory=lambda: float(
        os.environ.get("FEED_REFRESH_HOURS", "4")))
    feed_min_interval_minutes: float = field(default_factory=lambda: float(
        os.environ.get("FEED_MIN_INTERVAL_MINUTES", "60")))
    scheduler_enabled: bool = field(default_factory=lambda: _bool("SCHEDULER_ENABLED", True))
    # Single-user passcode. Leave empty to disable login (local use only).
    app_passcode: str = field(default_factory=lambda: os.environ.get("APP_PASSCODE", ""))
    secret_key: str = field(default_factory=lambda: os.environ.get("SECRET_KEY", ""))


_load_dotenv(BASE_DIR / ".env")
settings = Settings()
