"""APScheduler job registration for the AI news service.

Registers one daily cron trigger at 09:00 in the configured timezone,
plus a high-frequency ingest job that collects AI candidates every
30 minutes.
"""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path

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
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

# ------------------------------------------------------------------
# Ingest: high-frequency candidate collection (every 30 min)
# ------------------------------------------------------------------


async def run_ingest(
    tz: str = "Asia/Shanghai",
    failure_degraded_threshold: int = 3,
    publication_config=None,
):
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
    from app.content.clock import local_now

    run_started_at = local_now(tz).isoformat()
    all_items: list = []
    source_failures: list[str] = []
    skipped_sources: list[str] = []
    successful_sources: list[str] = []
    degraded_sources: list[dict] = []
    recent_seen_keys = set(store.load_recent_seen_canonical_keys())

    hf_proxy = os.getenv("HF_PROXY", "").strip() or None

    # AI / tool / game / digital 四类内容采集
    collector_specs = build_ingest_source_specs(hf_proxy=hf_proxy)

    for spec in collector_specs:
        started_at = time.perf_counter()
        status = "ok"
        failure_reason = None
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
                for failure in partial_failures:
                    feed_source, _, feed_error = failure.partition(":")
                    metrics_store.append_run_metric(
                        {
                            "source": f"rss:{feed_source}",
                            "run_id": ingest_run_id,
                            "run_started_at": run_started_at,
                            "raw_fetched_count": 0,
                            "deduped_new_count": 0,
                            "accepted_count": 0,
                            "selected_count": 0,
                            "rejected_duplicate_count": 0,
                            "rejected_quality_count": 0,
                            "duration_ms": 0,
                            "status": "error",
                            "failure_reason": feed_error.strip() or failure,
                        }
                    )
            successful_sources.append(spec.name)
            raw_items = [
                item
                for item in items
                if normalize_category(item.category) in {"ai", "tool", "game", "digital"}
            ]
        except Exception as e:
            if is_optional_source(spec):
                logger.warning("Ingest source skipped: %s (%s)", spec.name, e)
                skipped_sources.append(f"{spec.name}: {e}")
                status = "skipped"
                failure_reason = str(e)
            else:
                logger.exception("Ingest source failed: %s", spec.name)
                source_failures.append(f"{spec.name}: {e}")
                status = "error"
                failure_reason = str(e)

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
                "failure_reason": failure_reason,
            }
        )

        recent_metrics = metrics_store.aggregate_recent(spec.name, limit=24)
        updated_state = update_fetch_count_from_metrics(
            source_state,
            recent_metrics,
            run_started_at,
        )
        # RSS 部分 feed 失败已单独落指标，不能污染聚合 rss 来源的连续失败状态。
        if status in {"ok", "degraded"}:
            updated_state.update(
                consecutive_failure_count=0,
                last_success_at=run_started_at,
                last_error=None,
            )
        else:
            failures = int(source_state.get("consecutive_failure_count", 0)) + 1
            updated_state.update(
                consecutive_failure_count=failures,
                last_failure_at=run_started_at,
                last_error=failure_reason or status,
            )
            if failures >= failure_degraded_threshold:
                degraded_sources.append(
                    {
                        "source": spec.name,
                        "consecutive_failure_count": failures,
                        "last_error": failure_reason or status,
                    }
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
        "degraded_sources": degraded_sources,
    }
    IngestStatusStore().write_status(status_payload)

    if publication_config is not None:
        try:
            from app.classifiers.content_category_classifier import (
                ContentCategoryClassifier,
                dynamic_sources_from_feed_config,
            )
            from app.classifiers.relevance_filter import build_relevance_filter
            from app.content.source_policy import build_source_policy_registry
            from app.publication.locking import publication_write_lock
            from app.publication.publisher import Publisher
            from app.publication.retry_store import PublicationRetryStore
            from collectors.ai_rss import load_effective_feed_configuration

            async with publication_write_lock:
                publisher = Publisher.from_config(publication_config)
                if publisher is not None:
                    retry_store = PublicationRetryStore(_DATA_DIR)
                    article_replay_succeeded = True
                    try:
                        retry_store.replay_articles(publisher)
                    except Exception as exc:
                        logger.exception("Publication article replay failed")
                        article_replay_succeeded = False
                        status_payload["publication"] = {
                            "status": "pending",
                            "error": f"replay: {type(exc).__name__}",
                        }
                    if article_replay_succeeded:
                        try:
                            retry_store.replay_digests(publisher)
                        except Exception as exc:
                            logger.exception("Publication digest replay failed")
                            status_payload["publication"] = {
                                "status": "pending",
                                "error": f"digest_replay: {type(exc).__name__}",
                            }
                    if not all_items:
                        IngestStatusStore().write_status(status_payload)
                        return {"item_count": 0, "status": "no_items"}
                    feed_configuration = load_effective_feed_configuration() or {"feeds": {}}
                    policy_inputs = []
                    for category in ("ai", "tool", "game", "digital"):
                        policy_inputs.extend(
                            {**feed, "category": category}
                            for feed in feed_configuration.get("feeds", {}).get(category, [])
                            if isinstance(feed, dict)
                        )
                    policy_inputs.extend(
                        {**policy, "source": policy.get("source", source)}
                        for source, policy in feed_configuration.get("source_policies", {}).items()
                        if isinstance(policy, dict)
                    )
                    ContentCategoryClassifier().classify_batch(
                        all_items,
                        dynamic_sources=dynamic_sources_from_feed_config(feed_configuration),
                    )
                    publishable_items, _ = build_relevance_filter(
                        feed_configuration
                    ).evaluate_batch(all_items, build_source_policy_registry(policy_inputs))
                    try:
                        publisher.publish_candidates(publishable_items, feed_configuration)
                    except Exception as exc:
                        retry_store.enqueue_articles(publishable_items, feed_configuration)
                        logger.exception("Publication article write queued for retry")
                        status_payload["publication"] = {
                            "status": "pending",
                            "error": f"write: {type(exc).__name__}",
                        }
        except Exception as exc:
            logger.exception("Publication article write failed")
            status_payload["publication"] = {
                "status": "failed",
                "error": f"outbox: {type(exc).__name__}",
            }
            IngestStatusStore().write_status(status_payload)
        else:
            IngestStatusStore().write_status(status_payload)

    if all_items or source_failures:
        result = store.append_or_merge(all_items, source_failures=source_failures)
        return result

    return {"item_count": 0, "status": "no_items"}


async def run_ingest_with_cleanup(
    tz: str = "Asia/Shanghai",
    failure_degraded_threshold: int = 3,
    publication_config=None,
):
    """高频采集结束后分别清理候选池和发布库，二者故障互不掩盖。"""
    try:
        return await run_ingest(tz, failure_degraded_threshold, publication_config)
    finally:
        try:
            IngestionStore().prune_expired(keep_days=7)
        except Exception:
            # 候选池与发布库保留策略相互独立，前者失败时仍要尝试后者。
            logger.exception("Candidate cleanup failed")
        if publication_config is not None:
            try:
                from app.content.clock import local_now
                from app.publication.publisher import Publisher

                publisher = Publisher.from_config(publication_config)
                if publisher is not None:
                    publisher.store.cleanup_expired_publication(
                        local_today=local_now(tz).date(), tz=tz
                    )
            except Exception as exc:
                # 清理失败只反映发布库降级，不能改变已完成的采集结果或投递路径。
                logger.exception("Publication cleanup failed")
                try:
                    status_payload = IngestStatusStore().load_status()
                    status_payload["publication"] = {
                        "status": "degraded",
                        "error": f"cleanup: {type(exc).__name__}",
                    }
                    IngestStatusStore().write_status(status_payload)
                except Exception:
                    # 降级状态持久化只是可观测性增强，不能覆盖采集的原始结果或异常。
                    logger.exception("Publication cleanup degradation status write failed")


# ------------------------------------------------------------------
# Scheduler factory
# ------------------------------------------------------------------


def create_scheduler(
    agent, tz: str = "Asia/Shanghai", failure_degraded_threshold: int = 3, publication_config=None
) -> AsyncIOScheduler:
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
        args=[tz, failure_degraded_threshold, publication_config],
        max_instances=1,
        coalesce=True,
    )

    return scheduler
