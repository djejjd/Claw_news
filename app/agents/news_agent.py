"""News Agent — orchestration layer for the AI news pipeline.

Crawl -> Score -> Summarize -> Push, with lock-based concurrency control
and error-recovery push for failures.
"""

from __future__ import annotations

import asyncio
import logging

from aggregator.merger import position_score
from app.config import AppConfig
from app.tools.crawler import fetch_news
from app.tools.llm import summarize_news
from app.tools.wecom import send_text
from collectors.base import time_modifier

logger = logging.getLogger(__name__)

_TOP_N = 5
_KEYWORD_BONUS = 1.0


def _describe_exception(exc: Exception) -> str:
    """Return a stable exception description even when str(exc) is empty."""
    message = str(exc).strip()
    if message:
        return message
    return exc.__class__.__name__


class NewsAgent:
    """Orchestrates the AI news pipeline: crawl -> score -> summarize -> push.

    Uses an asyncio.Lock to prevent concurrent runs.  On failure at any
    stage, attempts to push an error notification to WeCom (if the webhook
    is configured).

    Usage::

        agent = NewsAgent(config)
        result = await agent.run_once()
        # result["status"] in {"ok", "failed", "skipped"}
    """

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_once(self) -> dict:
        """Execute one full news pipeline run.

        Returns a dict with keys:

        - **status**: ``"ok"`` | ``"failed"`` | ``"skipped"``
        - **fetched_count**: number of items retrieved from RSS
        - **pushed**: whether a message was successfully pushed to WeCom
        - **summary_preview**: first 200 chars of the LLM summary (or ``""``)
        - **errors**: list of error message strings
        """
        if self._lock.locked():
            logger.warning("Run lock is held — another run is in progress")
            return {
                "status": "skipped",
                "fetched_count": 0,
                "pushed": False,
                "summary_preview": "",
                "errors": ["another run is in progress"],
            }

        async with self._lock:
            return await self._run()

    # ------------------------------------------------------------------
    # Internal run
    # ------------------------------------------------------------------

    async def _run(self) -> dict:
        errors: list[str] = []
        fetched_count = 0
        pushed = False
        summary = ""
        summary_preview = ""

        # ---- Crawl -------------------------------------------------------
        logger.info("开始抓取新闻")
        try:
            items = await fetch_news(self._config.news_rss_urls, limit=10)
        except Exception as exc:
            detail = _describe_exception(exc)
            logger.error("新闻抓取失败: %s", detail)
            errors.append(f"crawl: {detail}")
            await self._try_push_error(f"新闻抓取失败: {detail}")
            return {
                "status": "failed",
                "fetched_count": 0,
                "pushed": True,
                "summary_preview": "",
                "errors": errors,
            }

        fetched_count = len(items)
        logger.info("抓取完成, 共 %d 条", fetched_count)

        if not items:
            logger.info("无新闻条目, 跳过后续步骤")
            return {
                "status": "skipped",
                "fetched_count": 0,
                "pushed": False,
                "summary_preview": "",
                "errors": [],
            }

        # ---- Score & select top 5 ----------------------------------------
        scored = self._score_items(items)
        top_items = scored[:_TOP_N]

        # ---- LLM Summarize -----------------------------------------------
        logger.info("开始总结")
        try:
            summary = await summarize_news(
                top_items,
                base_url=self._config.llm_base_url,
                api_key=self._config.llm_api_key,
                model=self._config.llm_model,
            )
        except Exception as exc:
            detail = _describe_exception(exc)
            logger.error("LLM 总结失败: %s", detail)
            errors.append(f"llm: {detail}")
            await self._try_push_error(f"LLM 总结失败: {detail}")
            return {
                "status": "failed",
                "fetched_count": fetched_count,
                "pushed": True,
                "summary_preview": "",
                "errors": errors,
            }

        logger.info("总结完成")
        summary_preview = summary[:200]

        # ---- Push --------------------------------------------------------
        logger.info("开始推送")
        try:
            await send_text(self._config.wecom_webhook_url, summary)
            pushed = True
            logger.info("推送完成")
        except Exception as exc:
            detail = _describe_exception(exc)
            logger.error("推送失败: %s", detail)
            errors.append(f"push: {detail}")
            return {
                "status": "failed",
                "fetched_count": fetched_count,
                "pushed": False,
                "summary_preview": summary_preview,
                "errors": errors,
            }

        return {
            "status": "ok",
            "fetched_count": fetched_count,
            "pushed": pushed,
            "summary_preview": summary_preview,
            "errors": errors,
        }

    # ------------------------------------------------------------------
    # Scoring helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _score_items(items: list[dict]) -> list[dict]:
        """Score each item via 3D RSS formula and return sorted desc.

        Formula: position_score(i+1) + keyword_bonus(1.0) + time_modifier(pub_date, "morning")
        """
        scored: list[tuple[float, dict]] = []
        for i, item in enumerate(items):
            pos_score = position_score(i + 1)
            tm_score = time_modifier(item.get("published_at", ""), "morning")
            score = pos_score + _KEYWORD_BONUS + tm_score
            scored.append((score, item))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored]

    # ------------------------------------------------------------------
    # Error recovery push
    # ------------------------------------------------------------------

    async def _try_push_error(self, message: str) -> None:
        """Attempt to push an error notification to the configured WeCom webhook.

        Failures here are logged but never propagated — error-recovery push
        is best-effort only.
        """
        if not self._config.wecom_webhook_url:
            return
        try:
            content = f"【AI News Service】运行异常\n{message}"
            await send_text(self._config.wecom_webhook_url, content)
            logger.info("已推送异常通知到 WeCom")
        except Exception as exc:
            logger.error("推送异常通知失败: %s", _describe_exception(exc))
