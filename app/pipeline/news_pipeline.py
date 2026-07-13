"""Unified news publishing pipeline — single entry point for all trigger modes."""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from aggregator.merger import Merger
from app.category_policy import display_category_for_runtime, normalize_category
from app.classifiers.topic_classifier import TopicClassifier
from app.delivery.state import ChannelResult, DeliveryState, make_delivery_id
from app.delivery.store import PendingDeliveryCorruptError, PendingDeliveryStore
from app.pipeline.context import RunContext
from app.renderers.telegram_html import render_telegram_digest
from app.renderers.wecom_markdown import make_preview, render_digest
from app.storage.github_exposure_store import GitHubExposureStore
from app.storage.github_store import GitHubStore
from app.storage.ingest_status_store import IngestStatusStore
from app.storage.ingestion_store import IngestionStore
from app.storage.source_metrics_store import SourceMetricsStore
from app.tools.llm import summarize_news
from app.tools.summary_result import DigestPayload, PublishResult, SummaryItem, SummaryResult
from infra.storage.state_store import StateStore
from pusher.telegram import TelegramError, TelegramPusher
from pusher.wecom import WeComPusher

logger = logging.getLogger(__name__)
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_TOPIC_LABELS = {
    "model_release": "模型",
    "agent_workflow": "Agent",
    "developer_tooling": "开源",
    "research_benchmark": "论文",
    "infrastructure": "工程",
    "application_case": "产品",
}


def _display_category_for(candidate) -> str:
    if candidate is None:
        return "AI"
    category = normalize_category(candidate.category)
    if category == "ai":
        if getattr(candidate, "topic", None) == "developer_tooling" or candidate.source == "github":
            return "工具"
    return display_category_for_runtime(category)


def _topic_label_for(candidate) -> str | None:
    return _TOPIC_LABELS.get(getattr(candidate, "topic", None) or "")


def _match_selected_candidate(selected: list, headline_item: dict):
    url = headline_item.get("url", "")
    title = headline_item.get("title", "")

    # 1. exact URL match
    if url:
        for candidate in selected:
            if candidate.url == url:
                return candidate

    # 2. canonical_key fallback（title 可能相同，置信度高于 title 匹配）
    if url:
        from app.pipeline.candidate import CandidateItem

        target_key = CandidateItem.make_canonical_key(url)
        if target_key:
            for candidate in selected:
                if getattr(candidate, "canonical_key", "") == target_key:
                    return candidate

    # 3. exact title match（最低优先级，最后手段）
    if title:
        for candidate in selected:
            if candidate.title == title:
                return candidate

    return None


def _collect_source_failures(ingest_status: dict) -> list[str]:
    """从本次 publish 启动时捕获的 ingest status 快照中读取失败源。"""
    return list(ingest_status.get("failed_sources", []))


def _config_string(config, name: str) -> str | None:
    value = getattr(config, name, None)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _has_telegram_delivery(config) -> bool:
    return bool(
        _config_string(config, "telegram_bot_token")
        and _config_string(config, "telegram_chat_id")
    )


def _pending_store() -> PendingDeliveryStore:
    return PendingDeliveryStore(_DATA_DIR)


def _delivery_state_from_payload(payload: dict) -> DeliveryState:
    channels = {
        name: ChannelResult(**channel_payload)
        for name, channel_payload in payload.get("channels", {}).items()
    }
    return DeliveryState(delivery_id=payload["delivery_id"], channels=channels)


def _make_channel_payload(
    enabled: bool,
    status: str,
    attempted_at: str | None = None,
    error: str | None = None,
) -> dict:
    return asdict(
        ChannelResult(enabled=enabled, status=status, attempted_at=attempted_at, error=error)
    )


def _build_headline_items(selected: list, llm_result: dict) -> tuple[list[SummaryItem], list[dict]]:
    summary_items: list[SummaryItem] = []
    payload_items: list[dict] = []
    for it in llm_result["headline_items"]:
        matched = _match_selected_candidate(selected, it)
        if not matched:
            continue
        summary_items.append(
            SummaryItem(
                title=it["title"],
                url=it["url"],
                core_summary=it["core_summary"],
                importance=it["importance"],
                trend=it["trend"],
                source=matched.source if matched else "",
                display_category=_display_category_for(matched) if matched else "AI",
                topic_label=_topic_label_for(matched) if matched else None,
            )
        )
        payload_items.append(
            {
                "title": it["title"],
                "url": it["url"],
                "core_summary": it["core_summary"],
                "importance": it["importance"],
                "trend": it["trend"],
                "source": matched.source if matched else "",
                "display_category": _display_category_for(matched) if matched else "AI",
                "topic_label": _topic_label_for(matched) if matched else None,
                "topic_confidence": getattr(matched, "topic_confidence", None) if matched else None,
                "final_score": getattr(matched, "final_score", None) if matched else None,
            }
        )
    return summary_items, payload_items


def _build_metric_rows(selected: list, now: datetime, tz: str) -> list[dict]:
    from app.content.time_policy import candidate_effective_at
    from app.content.time_policy import is_today as _time_is_today

    metric_rows = []
    for item in selected:
        eff, _ = candidate_effective_at(item)
        is_today_item = _time_is_today(eff, now, tz) if eff else False
        metric_rows.append(
            {
                "source": item.source,
                "category": item.category,
                "candidate_count": 1,
                "relevance_accepted_count": 1,
                "relevance_rejected_count": 0,
                "selected_today_count": 1 if is_today_item else 0,
                "selected_backfill_count": 0 if is_today_item else 1,
                "rejection_reasons": [],
            }
        )
    return metric_rows


def _build_github_projects_payload(github_ranked: list[dict]) -> list[dict]:
    return [
        {
            "full_name": r["item"].full_name,
            "final_score": r["final_score"],
            "activity": r["activity"],
            "popularity": r["popularity"],
            "relevance": r["relevance"],
            "penalty": r["penalty"],
            "recommendation": r["recommendation"],
            "matched_topics": r["item"].matched_topics,
            "matched_keywords": r["item"].matched_keywords,
        }
        for r in github_ranked
    ]


def _build_pending_payload(
    *,
    ctx: RunContext,
    markdown: str,
    telegram_messages: list[str],
    selected_count: int,
    daily_judgement: str,
    source_failures: list[str],
    headline_payload: list[dict],
    github_ranked: list[dict],
    github_recommendations: dict[str, str],
    published_urls: list[str],
    published_keys: list[str],
    selection_evidence: list[dict],
    relevance_rejected: list[dict],
    selected_counts_by_source: dict[str, int],
    metric_rows: list[dict],
) -> dict:
    date = ctx.time_window_start[:10]
    delivery_id = make_delivery_id(date, ctx.period, markdown)
    return {
        "delivery_id": delivery_id,
        "date": date,
        "period": ctx.period,
        "messages": {
            "wecom_markdown": markdown,
            "telegram_messages": telegram_messages,
        },
        "channels": {
            "wecom": _make_channel_payload(True, "pending"),
            "telegram": _make_channel_payload(True, "pending"),
        },
        "selected_count": selected_count,
        "finalization": {
            "date": date,
            "period": ctx.period,
            "trigger_mode": ctx.trigger_mode,
            "headline_items": headline_payload,
            "daily_judgement": daily_judgement,
            "source_failures": source_failures,
            "published_urls": published_urls,
            "published_keys": published_keys,
            "github_projects": _build_github_projects_payload(github_ranked),
            "github_recommendations": github_recommendations,
            "selection_evidence": selection_evidence,
            "relevance_rejections": relevance_rejected,
            "selected_counts_by_source": selected_counts_by_source,
            "metric_rows": metric_rows,
        },
    }


def _build_publish_payload_from_pending(
    pending_payload: dict,
    *,
    errors: list[str],
) -> DigestPayload:
    finalization = pending_payload["finalization"]
    return DigestPayload(
        date=finalization["date"],
        period=finalization["period"],
        published_at=datetime.now().isoformat(),
        trigger_mode=finalization["trigger_mode"],
        headline_items=finalization["headline_items"],
        daily_judgement=finalization["daily_judgement"],
        source_failures=finalization["source_failures"],
        published_urls=finalization["published_urls"],
        published_keys=finalization["published_keys"],
        github_projects=finalization["github_projects"],
        errors=errors,
        selection_evidence=finalization["selection_evidence"],
        relevance_rejections=finalization["relevance_rejections"],
    )


async def _attempt_wecom(markdown: str, webhook_url: str) -> tuple[bool, str | None]:
    try:
        result = await WeComPusher(webhook_url).push_single_markdown(markdown)
    except Exception as exc:
        return False, f"push: {exc}"
    if not result.success:
        return False, "push_failed"
    return True, None


async def _attempt_telegram(
    messages: list[str], bot_token: str, chat_id: str
) -> tuple[bool, str | None]:
    try:
        await TelegramPusher(bot_token, chat_id).push_messages(messages)
    except TelegramError as exc:
        return False, str(exc)
    except Exception as exc:
        return False, f"telegram_push: {type(exc).__name__}"
    return True, None


def _finalize_delivery(
    *,
    ctx: RunContext,
    pending_payload: dict,
    state_store: StateStore,
    metrics_store: SourceMetricsStore,
    exposure_store,
) -> list[str]:
    errors: list[str] = []
    finalization = pending_payload["finalization"]

    try:
        exposure_store.record([r["full_name"] for r in finalization["github_projects"]])
    except Exception:
        errors.append("github_exposure_write_failed")

    try:
        metrics_store.append_publish_source_metrics(
            datetime.now().isoformat(), finalization["metric_rows"]
        )
    except Exception:
        errors.append("publish_metrics_write_failed")

    try:
        written_sources = metrics_store.write_selected_counts(
            finalization["selected_counts_by_source"]
        )
        if written_sources < len(finalization["selected_counts_by_source"]):
            errors.append("source_metrics_write_failed")
    except Exception:
        errors.append("source_metrics_write_failed")

    try:
        state_store.merge_pushed_urls(set(finalization["published_urls"]))
        state_store.merge_published_keys(finalization["published_keys"])
        state_store.write_digest(
            _build_publish_payload_from_pending(pending_payload, errors=errors)
        )
    except Exception:
        errors.append("state_write_failed")

    return errors


def _update_pending_channel(
    pending_payload: dict, channel: str, status: str, error: str | None = None
) -> None:
    pending_payload["channels"][channel]["status"] = status
    pending_payload["channels"][channel]["attempted_at"] = datetime.now().isoformat()
    pending_payload["channels"][channel]["error"] = error


def _pending_completion_status(pending_payload: dict) -> tuple[str, bool, bool]:
    statuses = [channel.get("status") for channel in pending_payload.get("channels", {}).values()]
    any_succeeded = any(status == "succeeded" for status in statuses)
    all_succeeded = all(status == "succeeded" for status in statuses if status is not None)
    if all_succeeded and statuses:
        return "ok", True, True
    if any_succeeded:
        return "degraded", True, False
    return "failed", False, False


async def _resume_pending_delivery(
    *,
    ctx: RunContext,
    config,
    pending_payload: dict,
    state_store: StateStore,
    metrics_store: SourceMetricsStore,
    exposure_store,
    pending_store: PendingDeliveryStore,
) -> PublishResult:
    try:
        delivery_state = _delivery_state_from_payload(pending_payload)
    except Exception as exc:
        _write_publish_status(
            _make_publish_status("failed", 0, False, [f"pending_delivery_corrupt: {exc}"])
        )
        return PublishResult(
            status="failed",
            selected_count=0,
            pushed=False,
            message_type="markdown",
            summary_preview="",
            errors=[f"pending_delivery_corrupt: {exc}"],
        )

    if not _has_telegram_delivery(config):
        errors = ["telegram_config_missing"]
        _write_publish_status(
            _make_publish_status("failed", 0, False, errors)
        )
        return PublishResult(
            status="failed",
            selected_count=len(pending_payload["finalization"]["published_urls"]),
            pushed=False,
            message_type="markdown",
            summary_preview=make_preview(pending_payload["messages"]["wecom_markdown"]),
            errors=errors,
        )

    messages = pending_payload["messages"]
    finalization = pending_payload["finalization"]
    errors: list[str] = []
    selected_count = len(finalization["published_urls"])
    summary_preview = make_preview(messages["wecom_markdown"])

    if delivery_state.can_attempt("wecom"):
        ok, error = await _attempt_wecom(messages["wecom_markdown"], config.wecom_webhook_url)
        _update_pending_channel(
            pending_payload,
            "wecom",
            "succeeded" if ok else "failed",
            error,
        )
        if not ok and error:
            errors.append(error)
    if delivery_state.can_attempt("telegram"):
        ok, error = await _attempt_telegram(
            messages["telegram_messages"], config.telegram_bot_token, config.telegram_chat_id
        )
        _update_pending_channel(
            pending_payload,
            "telegram",
            "succeeded" if ok else "failed",
            error,
        )
        if not ok and error:
            errors.append(error)

    pending_store.save(ctx.time_window_start[:10], ctx.period, pending_payload)

    status, any_succeeded, all_succeeded = _pending_completion_status(pending_payload)
    if not any_succeeded:
        _write_publish_status(_make_publish_status(status, selected_count, False, errors))
        return PublishResult(
            status=status,
            selected_count=selected_count,
            pushed=False,
            message_type="markdown",
            summary_preview=summary_preview,
            errors=errors,
        )

    if not all_succeeded:
        _write_publish_status(_make_publish_status(status, selected_count, True, errors))
        return PublishResult(
            status=status,
            selected_count=selected_count,
            pushed=True,
            message_type="markdown",
            summary_preview=summary_preview,
            errors=errors,
        )

    final_errors = _finalize_delivery(
        ctx=ctx,
        pending_payload=pending_payload,
        state_store=state_store,
        metrics_store=metrics_store,
        exposure_store=exposure_store,
    )
    errors.extend(final_errors)
    status = "ok" if not errors else "degraded"
    _write_publish_status(_make_publish_status(status, selected_count, True, errors))
    if not final_errors:
        pending_store.delete(ctx.time_window_start[:10], ctx.period)
    return PublishResult(
        status=status,
        selected_count=selected_count,
        pushed=True,
        message_type="markdown",
        summary_preview=summary_preview,
        errors=errors,
    )


async def _deliver_with_pending(
    *,
    ctx: RunContext,
    config,
    markdown: str,
    telegram_messages: list[str],
    selected_count: int,
    daily_judgement: str,
    source_failures: list[str],
    headline_payload: list[dict],
    github_ranked: list[dict],
    github_recommendations: dict[str, str],
    published_urls: list[str],
    published_keys: list[str],
    selection_evidence: list[dict],
    relevance_rejected: list[dict],
    selected_counts_by_source: dict[str, int],
    metric_rows: list[dict],
    state_store: StateStore,
    metrics_store: SourceMetricsStore,
    exposure_store,
) -> PublishResult:
    pending_store = _pending_store()
    pending_payload = _build_pending_payload(
        ctx=ctx,
        markdown=markdown,
        telegram_messages=telegram_messages,
        selected_count=selected_count,
        daily_judgement=daily_judgement,
        source_failures=source_failures,
        headline_payload=headline_payload,
        github_ranked=github_ranked,
        github_recommendations=github_recommendations,
        published_urls=published_urls,
        published_keys=published_keys,
        selection_evidence=selection_evidence,
        relevance_rejected=relevance_rejected,
        selected_counts_by_source=selected_counts_by_source,
        metric_rows=metric_rows,
    )
    try:
        pending_store.save(ctx.time_window_start[:10], ctx.period, pending_payload)
    except Exception as exc:
        _write_publish_status(
            _make_publish_status("failed", selected_count, False, [f"pending_write_failed: {exc}"])
        )
        return PublishResult(
            status="failed",
            selected_count=selected_count,
            pushed=False,
            message_type="markdown",
            summary_preview=make_preview(markdown),
            errors=[f"pending_write_failed: {exc}"],
        )

    errors: list[str] = []
    wecom_ok, wecom_error = await _attempt_wecom(markdown, config.wecom_webhook_url)
    _update_pending_channel(
        pending_payload,
        "wecom",
        "succeeded" if wecom_ok else "failed",
        wecom_error,
    )
    if not wecom_ok and wecom_error:
        errors.append(wecom_error)
    try:
        pending_store.save(ctx.time_window_start[:10], ctx.period, pending_payload)
    except Exception as exc:
        errors.append(f"pending_write_failed: {exc}")

    telegram_ok = False
    telegram_error = None
    if _has_telegram_delivery(config):
        telegram_ok, telegram_error = await _attempt_telegram(
            telegram_messages, config.telegram_bot_token, config.telegram_chat_id
        )
        _update_pending_channel(
            pending_payload,
            "telegram",
            "succeeded" if telegram_ok else "failed",
            telegram_error,
        )
        if not telegram_ok and telegram_error:
            errors.append(telegram_error)
        try:
            pending_store.save(ctx.time_window_start[:10], ctx.period, pending_payload)
        except Exception as exc:
            errors.append(f"pending_write_failed: {exc}")

    status, any_succeeded, all_succeeded = _pending_completion_status(pending_payload)
    if not any_succeeded:
        _write_publish_status(
            _make_publish_status(status, selected_count, bool(wecom_ok or telegram_ok), errors)
        )
        return PublishResult(
            status=status,
            selected_count=selected_count,
            pushed=bool(wecom_ok or telegram_ok),
            message_type="markdown",
            summary_preview=make_preview(markdown),
            errors=errors,
        )

    if not all_succeeded:
        _write_publish_status(_make_publish_status(status, selected_count, True, errors))
        return PublishResult(
            status=status,
            selected_count=selected_count,
            pushed=True,
            message_type="markdown",
            summary_preview=make_preview(markdown),
            errors=errors,
        )

    final_errors = _finalize_delivery(
        ctx=ctx,
        pending_payload=pending_payload,
        state_store=state_store,
        metrics_store=metrics_store,
        exposure_store=exposure_store,
    )
    errors.extend(final_errors)
    status = "ok" if not errors else "degraded"
    _write_publish_status(_make_publish_status(status, selected_count, True, errors))
    if not final_errors:
        pending_store.delete(ctx.time_window_start[:10], ctx.period)
    return PublishResult(
        status=status,
        selected_count=selected_count,
        pushed=True,
        message_type="markdown",
        summary_preview=make_preview(markdown),
        errors=errors,
    )


async def run_pipeline(ctx: RunContext, config) -> PublishResult:
    """统一发布主链路。HTTP/scheduler/CLI 都走这条链路。

    1. 从 IngestionStore 读窗口内候选
    2. TopicClassifier 分类
    3. Merger 评分+选材 (use_new_scoring=True)
    4. LLM 摘要 → SummaryResult
    5. Markdown 渲染
    6. WeCom 单消息推送
    7. StateStore 持久化
    """
    state_store = StateStore(_DATA_DIR)
    pushed_urls = state_store.load_pushed_urls()
    pushed_keys = state_store.load_published_keys()
    ingestion_store = IngestionStore()
    ingest_status_snapshot = IngestStatusStore().load_status()
    metrics_store = SourceMetricsStore()
    pending_store = _pending_store()

    if _has_telegram_delivery(config):
        try:
            pending_payload = pending_store.load(ctx.time_window_start[:10], ctx.period)
        except PendingDeliveryCorruptError as exc:
            errors = [f"pending_delivery_corrupt: {exc}"]
            _write_publish_status(_make_publish_status("failed", 0, False, errors))
            return PublishResult(
                status="failed",
                selected_count=0,
                pushed=False,
                message_type="markdown",
                summary_preview="",
                errors=errors,
            )
        if pending_payload is not None:
            return await _resume_pending_delivery(
                ctx=ctx,
                config=config,
                pending_payload=pending_payload,
                state_store=state_store,
                metrics_store=metrics_store,
                exposure_store=GitHubExposureStore(),
                pending_store=pending_store,
            )

    # ---- Task 6: 统一发布链路 ----
    # 尝试走新路径；无法导入或 feeds.yaml 缺失时回退旧路径

    try:
        from collectors.ai_rss import load_feed_configuration

        feed_config = load_feed_configuration()
        use_new_pipeline = isinstance(feed_config, dict) and bool(feed_config.get("feeds"))
    except Exception:
        use_new_pipeline = False

    if use_new_pipeline:
        from app.classifiers.relevance_filter import build_relevance_filter
        from app.content.source_policy import build_source_policy_registry
        from app.pipeline.selection import select_digest
        from app.storage.ingestion_store import filter_unexpired_candidates

        candidates_used_historical = True
        relevance_rejected = []
        selection_result = None

        # 1. 构建 SourcePolicy registry
        feeds_raw = []
        for cat in ("ai", "tool", "game"):
            for f in feed_config.get("feeds", {}).get(cat, []):
                if isinstance(f, dict):
                    feeds_raw.append({**f, "category": cat})
        policies = build_source_policy_registry(feeds_raw)

        # 2. 72 小时读取
        now = datetime.now()
        window_end = now.isoformat()
        try:
            candidates = ingestion_store.load_recent_candidates(
                window_end,
                lookback_hours=72,
                pushed_urls=pushed_urls,
                pushed_keys=pushed_keys,
            )
        except Exception:
            logger.warning("历史候选读取失败，降级为当天窗口")
            candidates = ingestion_store.load_window_candidates(
                ctx.time_window_start,
                ctx.time_window_end,
                pushed_urls,
                pushed_keys,
            )
            candidates_used_historical = False

        if ctx.publish_scope == "ai_only":
            candidates = [i for i in candidates if i.category == "ai"]
        elif ctx.publish_scope == "all_digest":
            candidates = [i for i in candidates if i.category in {"ai", "tool", "game"}]

        if not candidates:
            _write_publish_status(_make_publish_status("skipped", 0, False, []))
            return PublishResult(
                status="skipped",
                selected_count=0,
                pushed=False,
                message_type="markdown",
                summary_preview="",
            )

        # 3. 按源有效期过滤
        candidates, expiry_rejected = filter_unexpired_candidates(candidates, now, policies)

        # 4. 相关性过滤
        rf = build_relevance_filter(feed_config)
        candidates, relevance_rejected = rf.evaluate_batch(candidates, policies)

        if not candidates:
            _write_publish_status(_make_publish_status("skipped", 0, False, []))
            return PublishResult(
                status="skipped",
                selected_count=0,
                pushed=False,
                message_type="markdown",
                summary_preview="",
            )

        # 5. 分类 + 三阶段选材
        TopicClassifier().classify_batch(candidates)
        selection_result = select_digest(candidates, policies, now, config.tz, top_n=10)
        selected = selection_result.selected
    else:
        # ---- 旧路径（测试兼容）----
        candidates_used_historical = False
        relevance_rejected = []
        selection_result = None
        now = datetime.now()

        candidates = ingestion_store.load_window_candidates(
            ctx.time_window_start,
            ctx.time_window_end,
            pushed_urls,
            pushed_keys,
        )
        if ctx.publish_scope == "ai_only":
            candidates = [i for i in candidates if i.category == "ai"]
        elif ctx.publish_scope == "all_digest":
            candidates = [i for i in candidates if i.category in {"ai", "tool", "game"}]

        if not candidates:
            _write_publish_status(_make_publish_status("skipped", 0, False, []))
            return PublishResult(
                status="skipped",
                selected_count=0,
                pushed=False,
                message_type="markdown",
                summary_preview="",
            )

        TopicClassifier().classify_batch(candidates)
        selected = Merger(top_n=10).merge(candidates, use_new_scoring=True)

    # 6. LLM 摘要（含 GitHub 项目中文翻译）
    items_for_llm = [
        {"title": it.title, "link": it.url, "summary": it.summary, "published_at": it.published_at}
        for it in selected
    ]
    github_raw = GitHubStore().load_latest_snapshot()
    # 综合评分 + 曝光惩罚 → top3
    from app.github_ranking import rank_and_recommend

    exposure_store = GitHubExposureStore()
    exposure_dates = exposure_store.load()
    github_ranked = rank_and_recommend(github_raw or [], exposure_dates, top_n=3)
    github_top3 = [r["item"] for r in github_ranked]
    github_recommendations = {r["item"].full_name: r["recommendation"] for r in github_ranked}

    github_dicts = [
        {
            "full_name": r.full_name,
            "description": r.description,
            "stars": r.stars,
            "language": r.language,
        }
        for r in github_top3
    ]
    llm_result = await summarize_news(
        items_for_llm,
        base_url=config.llm_base_url,
        api_key=config.llm_api_key,
        model=config.llm_model,
        github_projects=github_dicts if github_dicts else None,
    )
    if "_parse_error" in llm_result and not llm_result.get("headline_items"):
        _write_publish_status(
            _make_publish_status(
                "failed", len(selected), False, [f"llm_parse: {llm_result['_parse_error']}"]
            )
        )
        return PublishResult(
            status="failed",
            selected_count=len(selected),
            pushed=False,
            message_type="markdown",
            summary_preview="",
            errors=[f"llm_parse: {llm_result['_parse_error']}"],
        )

    # 5. 构建 SummaryResult
    headline_items, headline_payload = _build_headline_items(selected, llm_result)
    summary = SummaryResult(
        headline_items=headline_items,
        daily_judgement=llm_result["daily_judgement"],
        github_projects_cn=llm_result.get("github_projects", []),
    )

    # 6. 渲染 — 将 GitHub 描述替换为 LLM 翻译的中文版本
    translated_map: dict[str, str] = {
        p["full_name"]: p.get("description_cn", "") for p in llm_result.get("github_projects", [])
    }
    if github_top3 and translated_map:
        for item in github_top3:
            cn_desc = translated_map.get(item.full_name, "")
            if cn_desc:
                item.description = cn_desc
    # 附加推荐理由到 item（renderer 会读取）
    for item in github_top3:
        if item.full_name in github_recommendations:
            item.url = item.url  # keep
    markdown = render_digest(
        summary,
        github_items=github_top3,
        github_recommendations=github_recommendations,
        pushed_urls=pushed_urls,
    )
    telegram_messages = render_telegram_digest(
        summary,
        github_items=github_top3,
        github_recommendations=github_recommendations,
        pushed_urls=pushed_urls,
    )

    source_failures = _collect_source_failures(ingest_status_snapshot)
    selected_count = len(selected)
    published_urls = [it.url for it in selected]
    published_keys_list = [it.canonical_key for it in selected]
    selected_counts_by_source: dict[str, int] = {}
    for item in selected:
        selected_counts_by_source[item.source] = selected_counts_by_source.get(item.source, 0) + 1
    metric_rows = _build_metric_rows(selected, now, config.tz)
    selection_evidence = (
        [
            {
                "canonical_key": e.canonical_key,
                "phase": e.phase,
                "final_score": e.final_score,
                "diversity_penalty": e.diversity_penalty,
                "selection_score": e.selection_score,
            }
            for e in selection_result.evidence
        ]
        if selection_result
        else []
    )

    errors: list[str] = []
    if use_new_pipeline and not candidates_used_historical:
        errors.append("historical_candidates_read_failed")

    if _has_telegram_delivery(config):
        return await _deliver_with_pending(
            ctx=ctx,
            config=config,
            markdown=markdown,
            telegram_messages=telegram_messages,
            selected_count=selected_count,
            daily_judgement=summary.daily_judgement,
            source_failures=source_failures,
            headline_payload=headline_payload,
            github_ranked=github_ranked,
            github_recommendations=github_recommendations,
            published_urls=published_urls,
            published_keys=published_keys_list,
            selection_evidence=selection_evidence,
            relevance_rejected=relevance_rejected,
            selected_counts_by_source=selected_counts_by_source,
            metric_rows=metric_rows,
            state_store=state_store,
            metrics_store=metrics_store,
            exposure_store=GitHubExposureStore(),
        )

    # 7. 推送
    try:
        pr = await WeComPusher(config.wecom_webhook_url).push_single_markdown(markdown)
    except Exception as exc:
        _write_publish_status(
            _make_publish_status("failed", len(selected), False, [f"push: {exc}"])
        )
        return PublishResult(
            status="failed",
            selected_count=len(selected),
            pushed=False,
            message_type="markdown",
            summary_preview=make_preview(markdown),
            errors=[f"push: {exc}"],
        )
    if not pr.success:
        _write_publish_status(_make_publish_status("failed", len(selected), False, ["push_failed"]))
        return PublishResult(
            status="failed",
            selected_count=len(selected),
            pushed=False,
            message_type="markdown",
            summary_preview=make_preview(markdown),
            errors=["push_failed"],
        )

    # 推送成功后记录 GitHub 曝光
    exposure_store.record([r.full_name for r in github_top3])

    # 8. 状态持久化
    published_urls = [it.url for it in selected]

    # 独立 publish 指标（按真实 source 聚合）
    try:
        from app.content.time_policy import candidate_effective_at
        from app.content.time_policy import is_today as _time_is_today

        metric_rows = []
        for item in selected:
            eff, _ = candidate_effective_at(item)
            is_today_item = _time_is_today(eff, now, config.tz) if eff else False
            metric_rows.append(
                {
                    "source": item.source,
                    "category": item.category,
                    "candidate_count": 1,
                    "relevance_accepted_count": 1,
                    "relevance_rejected_count": 0,
                    "selected_today_count": 1 if is_today_item else 0,
                    "selected_backfill_count": 0 if is_today_item else 1,
                    "rejection_reasons": [],
                }
            )
        metrics_store.append_publish_source_metrics(now.isoformat(), metric_rows)
    except Exception:
        errors.append("publish_metrics_write_failed")

    # 状态持久化
    published_keys_list = [it.canonical_key for it in selected]
    selected_counts_by_source: dict[str, int] = {}
    for item in selected:
        selected_counts_by_source[item.source] = selected_counts_by_source.get(item.source, 0) + 1

    try:
        written_sources = metrics_store.write_selected_counts(selected_counts_by_source)
        if written_sources < len(selected_counts_by_source):
            errors.append("source_metrics_write_failed")
    except Exception:
        errors.append("source_metrics_write_failed")

    try:
        state_store.merge_pushed_urls(set(published_urls))
        state_store.merge_published_keys(published_keys_list)
        state_store.write_digest(
            DigestPayload(
                date=ctx.time_window_start[:10],
                period=ctx.period,
                published_at=datetime.now().isoformat(),
                trigger_mode=ctx.trigger_mode,
                headline_items=[
                    {
                        "title": it["title"],
                        "url": it["url"],
                        "core_summary": it["core_summary"],
                        "importance": it["importance"],
                        "trend": it["trend"],
                        "source": matched.source if matched else "",
                        "display_category": _display_category_for(matched) if matched else "AI",
                        "topic_label": _topic_label_for(matched) if matched else None,
                        "topic_confidence": getattr(matched, "topic_confidence", None)
                        if matched
                        else None,
                        "final_score": getattr(matched, "final_score", None) if matched else None,
                    }
                    for it in llm_result["headline_items"]
                    for matched in [_match_selected_candidate(selected, it)]
                ],
                daily_judgement=llm_result["daily_judgement"],
                source_failures=source_failures,
                published_urls=published_urls,
                published_keys=published_keys_list,
                github_projects=[
                    {
                        "full_name": r["item"].full_name,
                        "final_score": r["final_score"],
                        "activity": r["activity"],
                        "popularity": r["popularity"],
                        "relevance": r["relevance"],
                        "penalty": r["penalty"],
                        "recommendation": r["recommendation"],
                        "matched_topics": r["item"].matched_topics,
                        "matched_keywords": r["item"].matched_keywords,
                    }
                    for r in github_ranked
                ],
                errors=errors,
                selection_evidence=(
                    [
                        {
                            "canonical_key": e.canonical_key,
                            "phase": e.phase,
                            "final_score": e.final_score,
                            "diversity_penalty": e.diversity_penalty,
                            "selection_score": e.selection_score,
                        }
                        for e in selection_result.evidence
                    ]
                    if selection_result
                    else []
                ),
                relevance_rejections=relevance_rejected,
            )
        )
    except Exception:
        errors.append("state_write_failed")

    publish_ok = len(errors) == 0
    _write_publish_status(
        _make_publish_status("ok" if publish_ok else "degraded", len(selected), True, errors)
    )
    return PublishResult(
        status="ok" if publish_ok else "degraded",
        selected_count=len(selected),
        pushed=True,
        message_type="markdown",
        summary_preview=make_preview(markdown),
        errors=errors,
    )


def _make_publish_status(status, selected_count, pushed, errors):
    return {
        "status": status,
        "selected_count": selected_count,
        "pushed": pushed,
        "errors": errors,
        "recorded_at": datetime.now().isoformat(),
    }


def _write_publish_status(payload: dict) -> None:
    """写入 durable publish 状态，供 /health 和后续排查使用。"""
    path = _DATA_DIR / "publish_status.json"
    import json

    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
