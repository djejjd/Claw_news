"""APScheduler job registration for the AI news service.

Registers one daily cron trigger at 09:00 in the configured timezone,
plus a high-frequency ingest job that collects AI candidates every
30 minutes.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.ingest.source_policy import should_accept_candidate, update_fetch_count_from_metrics
from app.pipeline.candidate import CandidateItem
from app.storage.github_store import GitHubStore
from app.storage.ingest_status_store import IngestStatusStore
from app.storage.ingestion_store import IngestionStore
from app.storage.source_metrics_store import SourceMetricsStore
from app.storage.source_state_store import SourceStateStore
from collectors.base import hotitem_to_candidate

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Ingest: high-frequency candidate collection (every 30 min)
# ------------------------------------------------------------------


async def run_ingest():
    """Run all AI-relevant collectors, normalize to CandidateItem, write to Ingestion Store.

    Each collector is wrapped independently — one failure never
    interrupts the rest of the round.
    """
    import os

    from app.category_policy import normalize_category
    from app.ingest.source_registry import build_ingest_source_specs, is_optional_source
    from collectors.github import GitHubCollector

    store = IngestionStore()
    metrics_store = SourceMetricsStore()
    state_store = SourceStateStore()
    ingest_run_id = uuid.uuid4().hex[:12]
    run_started_at = datetime.now().isoformat()
    all_items: list = []
    source_failures: list[str] = []
    skipped_sources: list[str] = []
    successful_sources: list[str] = []
    recent_seen_keys = set(store.load_recent_seen_canonical_keys())

    hf_proxy = os.getenv("HF_PROXY", "").strip() or None

    # AI / tool / game 三类内容采集
    collector_specs = build_ingest_source_specs(hf_proxy=hf_proxy)

    for spec in collector_specs:
        started_at = time.perf_counter()
        status = "ok"
        raw_items = []
        source_state = state_store.load_state(spec.name, default_fetch_count=10)
        try:
            logger.info("Ingest source start: %s", spec.name)
            collector = spec.collector_cls(
                fetch_count=source_state["fetch_count"],
                **spec.collector_kwargs,
            )
            items = await collector.collect()
            logger.info("Ingest source done: %s items=%s", spec.name, len(items))
            # 检查 per-feed 部分失败（RSS 特有）
            partial_failures = getattr(collector, "failed_feeds", [])
            if partial_failures:
                skipped_sources.extend(f"{spec.name}:feed={f}" for f in partial_failures)
                status = "degraded"
            successful_sources.append(spec.name)
            raw_items = [i for i in items if normalize_category(i.category) in {"ai", "tool", "game"}]
        except Exception as e:
            if is_optional_source(spec):
                logger.warning("Ingest source skipped: %s (%s)", spec.name, e)
                skipped_sources.append(f"{spec.name}: {e}")
                status = "skipped"
            else:
                logger.exception("Ingest source failed: %s", spec.name)
                source_failures.append(f"{spec.name}: {e}")
                status = "error"

        deduped_items: list[tuple[str, object]] = []
        rejected_duplicate_count = 0
        rejected_quality_count = 0
        accepted_items = []
        source_seen_keys = set(recent_seen_keys)
        for item in raw_items:
            canonical_key = CandidateItem.make_canonical_key(item.url) if item.url else ""
            if not canonical_key or canonical_key in source_seen_keys:
                rejected_duplicate_count += 1
                continue

            source_seen_keys.add(canonical_key)
            deduped_items.append((canonical_key, item))

        for canonical_key, item in deduped_items:
            candidate = hotitem_to_candidate(item, ingest_run_id=ingest_run_id)
            if not should_accept_candidate(candidate):
                rejected_quality_count += 1
                continue

            accepted_items.append(candidate)
            recent_seen_keys.add(canonical_key)

        all_items.extend(accepted_items)

        duration_ms = int((time.perf_counter() - started_at) * 1000)
        metrics_store.append_run_metric(
            {
                "source": spec.name,
                "run_id": ingest_run_id,
                "run_started_at": run_started_at,
                "raw_fetched_count": len(raw_items),
                "deduped_new_count": len(deduped_items),
                "accepted_count": len(accepted_items),
                "selected_count": 0,
                "rejected_duplicate_count": rejected_duplicate_count,
                "rejected_quality_count": rejected_quality_count,
                "duration_ms": duration_ms,
                "status": status,
            }
        )

        recent_metrics = metrics_store.aggregate_recent(spec.name, limit=24)
        updated_state = update_fetch_count_from_metrics(
            source_state,
            recent_metrics,
            run_started_at,
        )
        state_store.save_state(spec.name, updated_state)

    try:
        logger.info("Ingest source start: github")
        github_items = await GitHubCollector().collect()
        GitHubStore().write_snapshot(github_items)
        logger.info("Ingest source done: github items=%s", len(github_items))
        successful_sources.append("github")
    except Exception as e:
        logger.exception("Ingest source failed: github")
        source_failures.append(f"github: {e}")

    status_payload = {
        "last_ingest_at": run_started_at,
        "last_item_count": len(all_items),
        "successful_sources": successful_sources,
        "failed_sources": source_failures,
        "skipped_sources": skipped_sources,
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
    scheduler.add_job(
        run_ingest_with_cleanup,
        "interval",
        minutes=30,
        id="ingest_30m",
        max_instances=1,
        coalesce=True,
    )

    return scheduler
