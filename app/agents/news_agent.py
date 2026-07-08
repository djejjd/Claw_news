"""News Agent — thin wrapper that delegates to the unified news pipeline.

Uses lock-based concurrency control and error-recovery push for failures.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from app.config import AppConfig
from app.pipeline.context import TriggerMode
from app.tools.wecom import send_text

logger = logging.getLogger(__name__)


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

    async def run_once(self, trigger_mode: TriggerMode = "scheduler") -> dict:
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
            return await self._run(trigger_mode)

    # ------------------------------------------------------------------
    # Internal run — delegates to unified pipeline
    # ------------------------------------------------------------------

    async def _run(self, trigger_mode: TriggerMode) -> dict:
        from app.pipeline.context import RunContext
        from app.pipeline.news_pipeline import run_pipeline

        now = datetime.now()
        ctx = RunContext(
            trigger_mode=trigger_mode,
            time_window_start=now.strftime("%Y-%m-%dT00:00:00"),
            time_window_end=now.strftime("%Y-%m-%dT%H:%M:%S"),
            publish_scope="all_digest" if trigger_mode in {"scheduler", "http"} else "ai_only",
        )

        try:
            result = await run_pipeline(ctx, self._config)
        except Exception as exc:
            detail = _describe_exception(exc)
            logger.error("Pipeline 执行失败: %s", detail)
            await self._try_push_error(f"Pipeline 执行失败: {detail}")
            return {
                "status": "failed",
                "fetched_count": 0,
                "pushed": True,
                "summary_preview": "",
                "errors": [f"pipeline: {detail}"],
            }

        return {
            "status": result.status,
            "fetched_count": result.selected_count,
            "pushed": result.pushed,
            "summary_preview": result.summary_preview,
            "errors": result.errors,
        }

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
