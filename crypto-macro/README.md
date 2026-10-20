# Crypto Macro

A personal, phone-first macro calendar laid out like the Forex Factory
calendar. It's built to alert you before and after high-impact economic
events, with an estimated volatility score for BTC/ETH. It's an installable
PWA (no app store) and shows all times in UK time (Europe/London).

> Scores estimate likely **volatility**, not price direction. Not financial advice.

## Status

| Phase | What | State |
|---|---|---|
| 1 | Calendar dashboard: feed fetch and cache, filters, countdown, dark mode | **done** |
| 2 | Web push: 30 min before high-impact USD events, "out now" alert, released-value alert from BLS/BEA, test button | next |
| 3 | Baseline impact score 0–10 | planned |
| 4 | Historical BTC reaction per event type (backfilled from past release dates and Binance 1-minute klines) | planned |
| 5 | Market-context modifier (open interest, funding, realised volatility, weekends) and surprise factor | planned |

## How it works

- **Backend:** Python (FastAPI) with SQLite. A background scheduler runs in the
  same process.
- **Feed fetching:** the backend fetches the Forex Factory weekly feed every 4
  hours. It also fetches a few extra times on Sundays, to pick up the new week
  when the feed rolls over.
- **Rate limit:** fetches are always at least 60 minutes apart, failed attempts
  included. If a fetch fails, the stored events stay as they are. The browser
  never calls the feed itself.
- **Times:** the feed's US Eastern times are stored in UTC and shown in UK
  time, so the weeks when US and UK clocks change on different dates come out
  right.
- **Swappable sources:** data providers sit behind small interfaces in
  `app/providers/base.py`. A paid calendar or an actual-values source can be
  plugged in there.

```
app/        backend (main.py, routes, db, scheduler, providers/)
web/        PWA frontend: plain HTML/CSS/JS, no build step
tests/      pytest tests with saved feed samples
scripts/    icon generator, offline seed script
```

## Local setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # APP_PASSCODE can stay empty locally
uvicorn app.main:create_app --factory --reload --port 8000
```

Open http://localhost:8000. The first feed fetch happens at startup.

To work offline, without touching the rate-limited feed:

```bash
SCHEDULER_ENABLED=0 uvicorn app.main:create_app --factory --port 8000
python scripts/seed_fixture.py tests/fixtures/ff_thisweek.json
```

Run the tests with `pytest`.

## Deployment (Fly.io, London)

The scheduler has to stay running to send alerts, so the host must not sleep.
On Fly.io, one always-on small machine plus a 1 GB volume costs roughly
$2–5/month, and HTTPS (which push notifications need) is included.

```bash
fly launch --copy-config --no-deploy      # set the app name in fly.toml
fly volumes create crypto_macro_data --region lhr --size 1
fly secrets set APP_PASSCODE='choose-one' SECRET_KEY="$(python -c 'import secrets;print(secrets.token_hex(32))')"
fly deploy
```

Run a single machine only (`fly scale count 1`). Two machines would mean two
schedulers, each sending its own copy of every alert.

As an alternative, any small VPS works (e.g. a Hetzner CX22 at about €4/month)
with `docker run -v /srv/crypto-macro:/data -p 8080:8080 --env-file .env`
behind Caddy for automatic HTTPS.

## Installing on your phone

The app has to be served over HTTPS, so use the deployed URL rather than
localhost.

**iPhone (iOS 16.4 or later)**
1. Open the site in **Safari** (other iOS browsers can't install web apps with push).
2. Tap Share → **Add to Home Screen** → Add.
3. Open it from the home-screen icon and enter your passcode.
4. Notifications (from phase 2): in the app, open Settings → *Enable
   notifications* → Allow. iOS only offers push to apps opened from the home
   screen. iOS can occasionally delay notifications, which is why the default
   alert is 30 minutes before the event.

**Android (Chrome)**
1. Open the site in Chrome.
2. Tap ⋮ → **Install app** (or *Add to Home screen*).
3. Open it and enter your passcode. Notifications are enabled the same way as on iPhone.

## Data sources and limits

- **Calendar:** Forex Factory weekly feed (`nfs.faireconomy.media`). It covers
  the current week only, and has forecast and previous values but no actuals.
  Next week's events appear when the feed rolls over at the weekend.
- **Actual values (phase 2):** BLS API (CPI, NFP, unemployment) and BEA API
  (PCE, GDP). Both are free, but you'll need to register for an API key.
- **History (phase 4):** past release dates come from FRED/ALFRED (free API
  key). BTC 1-minute klines come from `data.binance.vision` and the Binance
  public API. Every week's feed is also stored from now on.
