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

    if url:
        for candidate in selected:
            if candidate.url == url:
                return candidate

    if title:
        for candidate in selected:
            if candidate.title == title:
                return candidate

    return None


def _collect_source_failures(store: IngestionStore, start: str, end: str) -> list[str]:
    """聚合时间窗口内所有 index.json 的 source_failures。"""
    start_d = datetime.fromisoformat(start).date()
    end_d = datetime.fromisoformat(end).date()
    failures: set[str] = set()
    if not store.ingestion_dir.exists():
        return []
    for d in store.ingestion_dir.iterdir():
        if not d.is_dir():
            continue
        try:
            dir_date = date.fromisoformat(d.name)
        except ValueError:
            continue
        if not (start_d <= dir_date <= end_d):
            continue
        idx = store._load_index(d)
        if "source_failures" in idx:
            failures.update(idx["source_failures"])
    return sorted(failures)


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
    metrics_store = SourceMetricsStore()

    # 1. 读池
    candidates = ingestion_store.load_window_candidates(
        ctx.time_window_start, ctx.time_window_end, pushed_urls, pushed_keys
    )
    if ctx.publish_scope == "ai_only":
        candidates = [item for item in candidates if item.category == "ai"]
    elif ctx.publish_scope == "all_digest":
        candidates = [item for item in candidates if item.category in {"ai", "tool", "game"}]
    if not candidates:
        return PublishResult(
            status="skipped",
            selected_count=0,
            pushed=False,
            message_type="markdown",
            summary_preview="",
        )

    # 2. 分类
    TopicClassifier().classify_batch(candidates)

    # 3. 评分选材
    selected = Merger(top_n=10).merge(candidates, use_new_scoring=True)

    # 4. LLM 摘要（含 GitHub 项目中文翻译）
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

    source_failures = _collect_source_failures(
        ingestion_store,
        ctx.time_window_start,
        ctx.time_window_end,
    )

    # 7. 推送
    try:
        pr = await WeComPusher(config.wecom_webhook_url).push_single_markdown(markdown)
    except Exception as exc:
        return PublishResult(
            status="failed",
            selected_count=len(selected),
            pushed=False,
            message_type="markdown",
            summary_preview=make_preview(markdown),
            errors=[f"push: {exc}"],
        )
    if not pr.success:
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
    published_keys_list = [it.canonical_key for it in selected]
    selected_counts_by_source: dict[str, int] = {}
    for item in selected:
        selected_counts_by_source[item.source] = selected_counts_by_source.get(item.source, 0) + 1

    errors: list[str] = []
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
                    }
                    for it in llm_result["headline_items"]
                ],
                daily_judgement=llm_result["daily_judgement"],
                source_failures=source_failures,
                published_urls=published_urls,
                published_keys=published_keys_list,
                github_projects=llm_result.get("github_projects", []),
            )
        )
    except Exception:
        errors.append("state_write_failed")

    return PublishResult(
        status="ok",
        selected_count=len(selected),
        pushed=True,
        message_type="markdown",
        summary_preview=make_preview(markdown),
        errors=errors,
    )
