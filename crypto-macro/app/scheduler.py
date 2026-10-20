"""Background jobs. Runs inside the web process, so deploy a single worker."""

import logging
from datetime import timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .calendar_service import refresh_calendar
from .timeutil import utcnow

log = logging.getLogger(__name__)


def build_scheduler(state) -> AsyncIOScheduler:
    sched = AsyncIOScheduler(timezone="UTC")
    floor = timedelta(minutes=state.settings.feed_min_interval_minutes)

    async def feed_job():
        await refresh_calendar(state.db, state.provider, floor)

    sched.add_job(feed_job, "interval", hours=state.settings.feed_refresh_hours,
                  next_run_time=utcnow(), id="feed_refresh",
                  max_instances=1, coalesce=True)
    # The feed only covers the current week, so catch the weekend rollover
    # quickly enough for early-Monday alerts (London times).
    sched.add_job(feed_job, CronTrigger(day_of_week="sun", hour="6,18,23",
                                        minute=10, timezone="Europe/London"),
                  id="feed_rollover", max_instances=1, coalesce=True)
    return sched
