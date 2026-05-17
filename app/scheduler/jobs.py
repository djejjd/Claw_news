"""APScheduler job registration for the AI news service.

Registers three daily cron triggers at 09:00, 14:00, and 20:00
in the configured timezone.
"""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler


def create_scheduler(agent, tz: str = "Asia/Shanghai") -> AsyncIOScheduler:
    """Create and return a scheduler with news pipeline jobs registered.

    Args:
        agent: A NewsAgent instance whose ``run_once()`` is called.
        tz: IANA timezone name (e.g. ``"Asia/Shanghai"``).

    Returns:
        An AsyncIOScheduler with three cron jobs added. Caller is
        responsible for starting / shutting down the scheduler.
    """
    scheduler = AsyncIOScheduler(timezone=tz)

    scheduler.add_job(agent.run_once, "cron", hour=9, minute=0, id="news_0900")
    scheduler.add_job(agent.run_once, "cron", hour=14, minute=0, id="news_1400")
    scheduler.add_job(agent.run_once, "cron", hour=20, minute=0, id="news_2000")

    return scheduler
