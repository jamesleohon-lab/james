from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel

from .. import auth
from ..calendar_service import refresh_calendar
from ..providers.base import IMPACT_LEVELS
from ..providers.forexfactory import feed_week
from ..timeutil import LONDON, london_fields, parse_iso, to_utc_iso, utcnow

router = APIRouter(prefix="/api")


def _state(request: Request):
    return request.app.state


def serialize_event(row: dict, now: datetime) -> dict:
    starts_at = parse_iso(row["starts_at"])
    return {
        "id": row["id"],
        "country": row["country"],
        "title": row["title"],
        "impact": row["impact"],
        "starts_at": row["starts_at"],
        "all_day": bool(row["all_day"]),
        "forecast": row["forecast"],
        "previous": row["previous"],
        "actual": row["actual"],
        "is_past": starts_at <= now,
        **london_fields(starts_at),
    }


def week_bounds(now: datetime, offset: int) -> tuple[datetime, datetime]:
    """Sunday-to-Sunday window in London time, matching the FF week."""
    sunday = feed_week(now) + timedelta(weeks=offset)
    start = datetime(sunday.year, sunday.month, sunday.day, tzinfo=LONDON)
    end_day = sunday + timedelta(days=7)
    end = datetime(end_day.year, end_day.month, end_day.day, tzinfo=LONDON)
    return start, end


def _parse_filters(currencies: str | None, min_impact: str) -> tuple[list[str] | None, int]:
    if min_impact not in IMPACT_LEVELS:
        raise HTTPException(400, f"min_impact must be one of {list(IMPACT_LEVELS)}")
    codes = None
    if currencies and currencies.upper() != "ALL":
        codes = [c.strip().upper() for c in currencies.split(",") if c.strip()]
    return codes, IMPACT_LEVELS[min_impact]


@router.get("/health")
def health():
    return {"ok": True}


@router.get("/auth")
def auth_status(request: Request):
    s = _state(request).settings
    return {"required": bool(s.app_passcode),
            "authenticated": request.state.authenticated}


class LoginBody(BaseModel):
    passcode: str


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response):
    s = _state(request).settings
    if not s.app_passcode:
        return {"ok": True}
    if not auth.check_passcode(body.passcode, s.app_passcode):
        raise HTTPException(401, "wrong passcode")
    response.set_cookie(
        auth.COOKIE_NAME, auth.make_token(s.secret_key, s.app_passcode),
        max_age=auth.SESSION_DAYS * 86400, httponly=True, samesite="lax",
        secure=request.url.scheme == "https")
    return {"ok": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(auth.COOKIE_NAME)
    return {"ok": True}


@router.get("/events")
def events(request: Request,
           currencies: str | None = Query("USD", description="Comma list, or ALL"),
           min_impact: str = Query("high"),
           week: int = Query(0, ge=-104, le=1, description="0 = this week")):
    db = _state(request).db
    codes, rank = _parse_filters(currencies, min_impact)
    now = utcnow()
    start, end = week_bounds(now, week)
    rows = db.list_events(start, end, codes, rank)

    upcoming = [r for r in db.list_events(now, now + timedelta(days=21), codes, rank)
                if not r["all_day"]]
    next_event = serialize_event(upcoming[0], now) if upcoming else None

    last_ok = db.last_fetch(_state(request).provider.name, ok_only=True)
    last_any = db.last_fetch(_state(request).provider.name)
    return {
        "now": to_utc_iso(now),
        "week_start": start.date().isoformat(),
        "events": [serialize_event(r, now) for r in rows],
        "next_event": next_event,
        "feed": {
            "last_success_at": last_ok["fetched_at"] if last_ok else None,
            "last_error": last_any["error"] if last_any and not last_any["ok"] else None,
        },
    }


@router.get("/currencies")
def currencies(request: Request):
    known = _state(request).db.countries()
    return {"currencies": known or ["USD"]}


@router.post("/refresh")
async def refresh(request: Request):
    st = _state(request)
    return await refresh_calendar(
        st.db, st.provider, timedelta(minutes=st.settings.feed_min_interval_minutes))
