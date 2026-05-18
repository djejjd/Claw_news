"""APScheduler job registration for the AI news service.

Registers one daily cron trigger at 09:00 in the configured timezone,
plus a high-frequency ingest job that collects AI candidates every
30 minutes.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.storage.github_store import GitHubStore
from app.storage.ingest_status_store import IngestStatusStore
from app.storage.ingestion_store import IngestionStore
from collectors.base import hotitem_to_candidate

# ------------------------------------------------------------------
# Ingest: high-frequency candidate collection (every 30 min)
# ------------------------------------------------------------------


async def run_ingest():
    """Run all AI-relevant collectors, normalize to CandidateItem, write to Ingestion Store.

    Each collector is wrapped independently — one failure never
    interrupts the rest of the round.
    """
    import os

    from collectors.ai_rss import load_ai_rss_feeds
    from collectors.github import GitHubCollector
    from collectors.huggingface import HfDailyPapersCollector
    from collectors.rss_sources import RssCollector

    store = IngestionStore()
    ingest_run_id = uuid.uuid4().hex[:12]
    all_items: list = []
    source_failures: list[str] = []
    successful_sources: list[str] = []

    hf_proxy = os.getenv("HF_PROXY", "").strip() or None

    # AI-relevant collectors only (TapTap is game-focused, skip)
    collector_specs = [
        ("rss", RssCollector(feed_configs=load_ai_rss_feeds())),
        ("huggingface", HfDailyPapersCollector(proxy=hf_proxy)),
    ]

    for name, collector in collector_specs:
        try:
            items = await collector.collect()
            successful_sources.append(name)
            ai_items = [i for i in items if i.category == "ai"]
            for item in ai_items:
                candidate = hotitem_to_candidate(item, ingest_run_id=ingest_run_id)
                all_items.append(candidate)
        except Exception as e:
            source_failures.append(f"{name}: {e}")

    try:
        github_items = await GitHubCollector().collect()
        GitHubStore().write_snapshot(github_items)
        successful_sources.append("github")
    except Exception as e:
        source_failures.append(f"github: {e}")

    status_payload = {
        "last_ingest_at": datetime.now().isoformat(),
        "last_item_count": len(all_items),
        "successful_sources": successful_sources,
        "failed_sources": source_failures,
    }
    IngestStatusStore().write_status(status_payload)

    if all_items or source_failures:
        result = store.append_or_merge(all_items, source_failures=source_failures)
        return result

    return {"item_count": 0, "status": "no_items"}


async def run_ingest_with_cleanup():
    """Ingest + expire stale candidates beyond 3 days."""
    await run_ingest()
    store = IngestionStore()
    store.prune_expired(keep_days=3)


# ------------------------------------------------------------------
# Scheduler factory
# ------------------------------------------------------------------


def create_scheduler(agent, tz: str = "Asia/Shanghai") -> AsyncIOScheduler:
    """Create and return a scheduler with news pipeline jobs registered.

    Args:
        agent: A NewsAgent instance whose ``run_once()`` is called.
        tz: IANA timezone name (e.g. ``"Asia/Shanghai"``).

    Returns:
        An AsyncIOScheduler with two jobs added. Caller is
        responsible for starting / shutting down the scheduler.
    """
    scheduler = AsyncIOScheduler(timezone=tz)

    # Daily news pipeline — single publish at 09:00
    scheduler.add_job(agent.run_once, "cron", hour=9, minute=0, id="publish_0900")

    # High-frequency ingest: every 30 minutes, 00:00–23:59
    scheduler.add_job(run_ingest_with_cleanup, "interval", minutes=30, id="ingest_30m")

    return scheduler
