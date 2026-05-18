"""Unified news publishing pipeline — single entry point for all trigger modes."""

from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path

from aggregator.merger import Merger
from app.classifiers.topic_classifier import TopicClassifier
from app.pipeline.context import RunContext
from app.renderers.wecom_markdown import make_preview, render_digest
from app.storage.ingestion_store import IngestionStore
from app.tools.llm import summarize_news
from app.tools.summary_result import DigestPayload, PublishResult, SummaryItem, SummaryResult
from infra.storage.state_store import StateStore
from pusher.wecom import WeComPusher

logger = logging.getLogger(__name__)
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


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

    # 1. 读池
    candidates = ingestion_store.load_window_candidates(
        ctx.time_window_start, ctx.time_window_end, pushed_urls, pushed_keys
    )
    if ctx.publish_scope == "ai_only":
        candidates = [item for item in candidates if item.category == "ai"]
    if not candidates:
        return PublishResult(
            status="skipped", selected_count=0, pushed=False,
            message_type="markdown", summary_preview="",
        )

    # 2. 分类
    TopicClassifier().classify_batch(candidates)

    # 3. 评分选材
    selected = Merger(top_n=5).merge(candidates, use_new_scoring=True)

    # 4. LLM 摘要
    items_for_llm = [
        {"title": it.title, "link": it.url,
         "summary": it.summary, "published_at": it.published_at}
        for it in selected
    ]
    llm_result = await summarize_news(
        items_for_llm,
        base_url=config.llm_base_url,
        api_key=config.llm_api_key,
        model=config.llm_model,
    )
    if "_parse_error" in llm_result and not llm_result.get("headline_items"):
        return PublishResult(
            status="failed", selected_count=len(selected), pushed=False,
            message_type="markdown", summary_preview="",
            errors=[f"llm_parse: {llm_result['_parse_error']}"],
        )

    # 5. 构建 SummaryResult
    headline_items = [
        SummaryItem(
            title=it["title"], url=it["url"],
            core_summary=it["core_summary"],
            importance=it["importance"], trend=it["trend"],
        )
        for it in llm_result["headline_items"]
    ]
    summary = SummaryResult(
        headline_items=headline_items,
        daily_judgement=llm_result["daily_judgement"],
    )

    # 6. 渲染 & 收集 source_failures
    markdown = render_digest(summary)
    source_failures = _collect_source_failures(
        ingestion_store, ctx.time_window_start, ctx.time_window_end,
    )

    # 7. 推送
    try:
        pr = await WeComPusher(config.wecom_webhook_url).push_single_markdown(markdown)
    except Exception as exc:
        return PublishResult(
            status="failed", selected_count=len(selected), pushed=False,
            message_type="markdown", summary_preview=make_preview(markdown),
            errors=[f"push: {exc}"],
        )
    if not pr.success:
        return PublishResult(
            status="failed", selected_count=len(selected), pushed=False,
            message_type="markdown", summary_preview=make_preview(markdown),
            errors=["push_failed"],
        )

    # 8. 状态持久化
    published_urls = [it.url for it in selected]
    published_keys_list = [it.canonical_key for it in selected]
    try:
        state_store.merge_pushed_urls(set(published_urls))
        state_store.merge_published_keys(published_keys_list)
        state_store.write_digest(DigestPayload(
            date=ctx.time_window_start[:10],
            period=ctx.period,
            published_at=datetime.now().isoformat(),
            trigger_mode=ctx.trigger_mode,
            headline_items=[{
                "title": it["title"], "url": it["url"],
                "core_summary": it["core_summary"],
                "importance": it["importance"], "trend": it["trend"],
            } for it in llm_result["headline_items"]],
            daily_judgement=llm_result["daily_judgement"],
            source_failures=source_failures,
            published_urls=published_urls,
            published_keys=published_keys_list,
        ))
    except Exception:
        return PublishResult(
            status="ok", selected_count=len(selected), pushed=True,
            message_type="markdown", summary_preview=make_preview(markdown),
            errors=["state_write_failed"],
        )

    return PublishResult(
        status="ok", selected_count=len(selected), pushed=True,
        message_type="markdown", summary_preview=make_preview(markdown),
    )
