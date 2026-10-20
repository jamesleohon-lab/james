"""Load a saved feed file into the database, for offline development.

    python scripts/seed_fixture.py tests/fixtures/ff_thisweek.json
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.db import Database  # noqa: E402
from app.providers.forexfactory import parse_feed  # noqa: E402

if __name__ == "__main__":
    raw = Path(sys.argv[1]).read_text()
    db = Database(settings.database_path)
    print(db.sync_events("forexfactory", parse_feed(raw)))
