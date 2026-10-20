"""App entry point: `uvicorn app.main:create_app --factory` (one worker; see README)."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import auth
from .api.routes import router
from .calendar_service import restore_from_cache
from .config import BASE_DIR, Settings, settings as default_settings
from .db import Database
from .providers.forexfactory import ForexFactoryProvider
from .scheduler import build_scheduler

log = logging.getLogger(__name__)

PUBLIC_API = {"/api/health", "/api/auth", "/api/login", "/api/logout"}


def create_app(settings: Settings | None = None, provider=None) -> FastAPI:
    settings = settings or default_settings

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        restore_from_cache(app.state.db, app.state.provider)
        sched = None
        if settings.scheduler_enabled:
            sched = build_scheduler(app.state)
            sched.start()
        yield
        if sched:
            sched.shutdown(wait=False)

    app = FastAPI(title="Crypto Macro", lifespan=lifespan)
    app.state.settings = settings
    app.state.db = Database(settings.database_path)
    app.state.provider = provider or ForexFactoryProvider(settings.ff_feed_url)

    if not settings.app_passcode:
        log.warning("APP_PASSCODE is not set: the app is open to anyone who can reach it")

    @app.middleware("http")
    async def require_login(request: Request, call_next):
        ok = not settings.app_passcode or auth.check_token(
            request.cookies.get(auth.COOKIE_NAME), settings.secret_key, settings.app_passcode)
        request.state.authenticated = ok
        path = request.url.path
        if path.startswith("/api/") and path not in PUBLIC_API and not ok:
            return JSONResponse({"detail": "login required"}, status_code=401)
        return await call_next(request)

    app.include_router(router)
    app.mount("/", StaticFiles(directory=BASE_DIR / "web", html=True), name="web")
    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
