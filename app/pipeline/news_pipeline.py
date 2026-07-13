"""Unified news publishing pipeline — single entry point for all trigger modes."""

from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path

from aggregator.merger import Merger
from app.category_policy import display_category_for_runtime, normalize_category
from app.classifiers.topic_classifier import TopicClassifier
from app.pipeline.context import RunContext
from app.renderers.wecom_markdown import make_preview, render_digest
from app.storage.github_store import GitHubStore
from app.storage.ingest_status_store import IngestStatusStore
from app.storage.ingestion_store import IngestionStore
from app.storage.source_metrics_store import SourceMetricsStore
from app.tools.llm import summarize_news
from app.tools.summary_result import DigestPayload, PublishResult, SummaryItem, SummaryResult
from infra.storage.state_store import StateStore
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

    # ---- Task 6: 统一发布链路 ----
    # 尝试走新路径；无法导入或 feeds.yaml 缺失时回退旧路径

    try:
        from collectors.ai_rss import load_feed_configuration
        feed_config = load_feed_configuration()
        use_new_pipeline = (
            isinstance(feed_config, dict)
            and bool(feed_config.get("feeds"))
        )
    except Exception:
        use_new_pipeline = False

    if use_new_pipeline:
        from app.content.source_policy import build_source_policy_registry
        from app.storage.ingestion_store import filter_unexpired_candidates
        from app.classifiers.relevance_filter import build_relevance_filter
        from app.pipeline.selection import select_digest

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
                window_end, lookback_hours=72,
                pushed_urls=pushed_urls, pushed_keys=pushed_keys,
            )
        except Exception:
            logger.warning("历史候选读取失败，降级为当天窗口")
            candidates = ingestion_store.load_window_candidates(
                ctx.time_window_start, ctx.time_window_end, pushed_urls, pushed_keys,
            )
            candidates_used_historical = False

        if ctx.publish_scope == "ai_only":
            candidates = [i for i in candidates if i.category == "ai"]
        elif ctx.publish_scope == "all_digest":
            candidates = [i for i in candidates if i.category in {"ai", "tool", "game"}]

        if not candidates:
            _write_publish_status(_make_publish_status("skipped", 0, False, []))
            return PublishResult(status="skipped", selected_count=0, pushed=False,
                                 message_type="markdown", summary_preview="")

        # 3. 按源有效期过滤
        candidates, expiry_rejected = filter_unexpired_candidates(candidates, now, policies)

        # 4. 相关性过滤
        rf = build_relevance_filter(feed_config)
        candidates, relevance_rejected = rf.evaluate_batch(candidates, policies)

        if not candidates:
            _write_publish_status(_make_publish_status("skipped", 0, False, []))
            return PublishResult(status="skipped", selected_count=0, pushed=False,
                                 message_type="markdown", summary_preview="")

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
            ctx.time_window_start, ctx.time_window_end, pushed_urls, pushed_keys,
        )
        if ctx.publish_scope == "ai_only":
            candidates = [i for i in candidates if i.category == "ai"]
        elif ctx.publish_scope == "all_digest":
            candidates = [i for i in candidates if i.category in {"ai", "tool", "game"}]

        if not candidates:
            _write_publish_status(_make_publish_status("skipped", 0, False, []))
            return PublishResult(status="skipped", selected_count=0, pushed=False,
                                 message_type="markdown", summary_preview="")

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
    from app.storage.github_exposure_store import GitHubExposureStore

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
        _write_publish_status(_make_publish_status(
            "failed", len(selected), False, [f"llm_parse: {llm_result['_parse_error']}"]))
        return PublishResult(
            status="failed",
            selected_count=len(selected),
            pushed=False,
            message_type="markdown",
            summary_preview="",
            errors=[f"llm_parse: {llm_result['_parse_error']}"],
        )

    # 5. 构建 SummaryResult
    headline_items = [
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
        for it in llm_result["headline_items"]
        for matched in [_match_selected_candidate(selected, it)]
    ]
    summary = SummaryResult(
        headline_items=headline_items,
        daily_judgement=llm_result["daily_judgement"],
        github_projects_cn=llm_result.get("github_projects", []),
    )

    # 6. 渲染 — 将 GitHub 描述替换为 LLM 翻译的中文版本
    translated_map: dict[str, str] = {
        p["full_name"]: p.get("description_cn", "")
        for p in llm_result.get("github_projects", [])
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

    source_failures = _collect_source_failures(ingest_status_snapshot)

    errors: list[str] = []
    if use_new_pipeline and not candidates_used_historical:
        errors.append("historical_candidates_read_failed")

    # 7. 推送
    try:
        pr = await WeComPusher(config.wecom_webhook_url).push_single_markdown(markdown)
    except Exception as exc:
        _write_publish_status(_make_publish_status("failed", len(selected), False, [f"push: {exc}"]))
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
        from app.content.time_policy import candidate_effective_at, is_today as _time_is_today

        metric_rows = []
        for item in selected:
            eff, _ = candidate_effective_at(item)
            is_today_item = _time_is_today(eff, now, config.tz) if eff else False
            metric_rows.append({
                "source": item.source,
                "category": item.category,
                "candidate_count": 1,
                "relevance_accepted_count": 1,
                "relevance_rejected_count": 0,
                "selected_today_count": 1 if is_today_item else 0,
                "selected_backfill_count": 0 if is_today_item else 1,
                "rejection_reasons": [],
            })
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
                        "topic_confidence": matched.topic_confidence if matched else None,
                        "final_score": matched.final_score if matched else None,
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
                        {"canonical_key": e.canonical_key, "phase": e.phase,
                         "final_score": e.final_score, "diversity_penalty": e.diversity_penalty,
                         "selection_score": e.selection_score}
                        for e in selection_result.evidence
                    ] if selection_result else []
                ),
                relevance_rejections=relevance_rejected,
            )
        )
    except Exception:
        errors.append("state_write_failed")

    publish_ok = len(errors) == 0
    _write_publish_status(_make_publish_status(
        "ok" if publish_ok else "degraded", len(selected), True, errors))
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
