"""Tests for app/agents/news_agent.py — NewsAgent orchestration layer.

Covers:
- Full pipeline success (delegates to run_pipeline)
- No news path (pipeline returns skipped)
- Pipeline exception path (error -> error summary pushed)
- Push failure path (pipeline returns failed)
- Lock conflict (concurrent call -> skipped)
- Agent result mapping (summary_preview, selected_count, etc.)
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.config import AppConfig
from app.tools.summary_result import PublishResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WEBHOOK = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test-key"


def _make_config(**kwargs) -> AppConfig:
    return AppConfig(
        llm_api_key="test-api-key-12345",
        llm_base_url="https://api.example.com",
        llm_model="test-model",
        wecom_webhook_url=WEBHOOK,
        tz="Asia/Shanghai",
        news_rss_urls=["https://feed1.com/rss", "https://feed2.com/rss"],
        **kwargs,
    )


SUMMARY = (
    "今日 AI 新闻摘要\n\n"
    "1. [AI新闻标题 0](https://example.com/news/0)\n"
    "   - 核心内容：测试摘要\n"
    "   - 重要性：高\n"
    "   - 趋势判断：利好\n\n"
    "今日一句话判断：AI行业持续发展"
)

SUMMARY_PREVIEW = SUMMARY[:200]


def _make_publish_result(
    *,
    status: str = "ok",
    selected_count: int = 8,
    pushed: bool = True,
    summary_preview: str = SUMMARY_PREVIEW,
    errors: list | None = None,
) -> PublishResult:
    if errors is None:
        errors = []
    return PublishResult(
        status=status,
        selected_count=selected_count,
        pushed=pushed,
        message_type="markdown",
        summary_preview=summary_preview,
        errors=errors,
    )


# ===================================================================
# 1. Successful full pipeline
# ===================================================================


class TestNewsAgentSuccess:
    """Happy path: run_pipeline returns ok."""

    @pytest.mark.asyncio
    async def test_full_pipeline_ok(self):
        from app.agents.news_agent import NewsAgent

        config = _make_config()
        mock_result = _make_publish_result()

        with patch(
            "app.pipeline.news_pipeline.run_pipeline",
            new=AsyncMock(return_value=mock_result),
        ) as mock_pipeline:
            agent = NewsAgent(config)
            result = await agent.run_once()

        assert result["status"] == "ok"
        assert result["fetched_count"] == 8
        assert result["pushed"] is True
        assert SUMMARY_PREVIEW in result["summary_preview"]
        assert result["errors"] == []

        mock_pipeline.assert_called_once()

    @pytest.mark.asyncio
    async def test_selected_count_reflects_pipeline_result(self):
        """When pipeline selects 5 items, agent reports 5."""
        from app.agents.news_agent import NewsAgent

        config = _make_config()
        mock_result = _make_publish_result(selected_count=5)

        with patch(
            "app.pipeline.news_pipeline.run_pipeline",
            new=AsyncMock(return_value=mock_result),
        ):
            agent = NewsAgent(config)
            result = await agent.run_once()

        assert result["status"] == "ok"
        assert result["fetched_count"] == 5


# ===================================================================
# 2. No news path
# ===================================================================


class TestNoNews:
    """When pipeline returns skipped, agent should report skipped."""

    @pytest.mark.asyncio
    async def test_no_items_skips_pipeline(self):
        from app.agents.news_agent import NewsAgent

        config = _make_config()
        mock_result = _make_publish_result(
            status="skipped",
            selected_count=0,
            pushed=False,
            summary_preview="",
            errors=[],
        )

        with patch(
            "app.pipeline.news_pipeline.run_pipeline",
            new=AsyncMock(return_value=mock_result),
        ) as mock_pipeline:
            agent = NewsAgent(config)
            result = await agent.run_once()

        assert result["status"] == "skipped"
        assert result["fetched_count"] == 0
        assert result["pushed"] is False
        assert result["summary_preview"] == ""
        assert result["errors"] == []

        mock_pipeline.assert_called_once()


# ===================================================================
# 3. Pipeline exception path (covers both crawl & LLM errors)
# ===================================================================


class TestCrawlFailure:
    """When run_pipeline raises, error is logged and error summary pushed."""

    @pytest.mark.asyncio
    async def test_crawl_error_pushes_error_summary(self, caplog):
        from app.agents.news_agent import NewsAgent

        config = _make_config()

        with (
            patch(
                "app.pipeline.news_pipeline.run_pipeline",
                side_effect=RuntimeError("RSS feed down"),
            ),
            patch(
                "app.agents.news_agent.send_text",
                new=AsyncMock(return_value={"errcode": 0, "errmsg": "ok"}),
            ) as mock_push,
        ):
            agent = NewsAgent(config)
            result = await agent.run_once()

        assert result["status"] == "failed"
        assert result["fetched_count"] == 0
        assert result["pushed"] is True  # error summary was pushed
        assert len(result["errors"]) > 0
        assert any("pipeline" in e for e in result["errors"])

        # Verify error was pushed
        mock_push.assert_called_once()
        call_args = mock_push.call_args
        pushed_content = call_args[0][1]
        assert "RSS feed down" in pushed_content or "运行异常" in pushed_content

        # Verify error was logged
        assert any(
            "抓取失败" in r.message or "RSS feed down" in r.message or "Pipeline" in r.message
            for r in caplog.records
            if r.levelname in ("ERROR", "WARNING")
        )


# ===================================================================
# 4. LLM failure path (pipeline raises)
# ===================================================================


class TestLLMFailure:
    """When run_pipeline raises (e.g. LLM fails), error is pushed."""

    @pytest.mark.asyncio
    async def test_llm_error_pushes_error_summary(self):
        from app.agents.news_agent import NewsAgent

        config = _make_config()

        with (
            patch(
                "app.pipeline.news_pipeline.run_pipeline",
                side_effect=RuntimeError("LLM API 500"),
            ),
            patch(
                "app.agents.news_agent.send_text",
                new=AsyncMock(return_value={"errcode": 0, "errmsg": "ok"}),
            ) as mock_push,
        ):
            agent = NewsAgent(config)
            result = await agent.run_once()

        assert result["status"] == "failed"
        assert result["fetched_count"] == 0
        assert result["pushed"] is True  # error summary was pushed
        assert len(result["errors"]) > 0
        assert any("pipeline" in e for e in result["errors"])

        # Verify error was pushed
        mock_push.assert_called_once()
        call_args = mock_push.call_args
        pushed_content = call_args[0][1]
        assert "LLM" in pushed_content or "运行异常" in pushed_content

    @pytest.mark.asyncio
    async def test_llm_error_does_not_attempt_primary_push(self):
        """After pipeline raises, only the error notification is pushed."""
        from app.agents.news_agent import NewsAgent

        config = _make_config()

        with (
            patch(
                "app.pipeline.news_pipeline.run_pipeline",
                side_effect=RuntimeError("LLM API 500"),
            ),
            patch(
                "app.agents.news_agent.send_text",
                new=AsyncMock(return_value={"errcode": 0, "errmsg": "ok"}),
            ) as mock_push,
        ):
            agent = NewsAgent(config)
            await agent.run_once()

        # Exactly one push call — the error summary, not the LLM output
        assert mock_push.call_count == 1
        call_args = mock_push.call_args
        pushed_content = call_args[0][1]
        assert SUMMARY not in pushed_content

    @pytest.mark.asyncio
    async def test_llm_error_without_message_reports_exception_type(self):
        """Empty exception messages should still produce a diagnosable error string."""
        from app.agents.news_agent import NewsAgent

        class SilentLLMError(RuntimeError):
            def __str__(self) -> str:
                return ""

        config = _make_config()

        with (
            patch(
                "app.pipeline.news_pipeline.run_pipeline",
                side_effect=SilentLLMError(),
            ),
            patch(
                "app.agents.news_agent.send_text",
                new=AsyncMock(return_value={"errcode": 0, "errmsg": "ok"}),
            ),
        ):
            agent = NewsAgent(config)
            result = await agent.run_once()

        assert result["status"] == "failed"
        assert result["errors"] == ["pipeline: SilentLLMError"]


# ===================================================================
# 5. Push failure path (pipeline returns failed)
# ===================================================================


class TestPushFailure:
    """When pipeline returns status='failed', the agent reports it."""

    @pytest.mark.asyncio
    async def test_push_failure_returns_failed(self):
        from app.agents.news_agent import NewsAgent

        config = _make_config()
        mock_result = _make_publish_result(
            status="failed",
            selected_count=5,
            pushed=False,
            errors=["push_failed"],
        )

        with patch(
            "app.pipeline.news_pipeline.run_pipeline",
            new=AsyncMock(return_value=mock_result),
        ):
            agent = NewsAgent(config)
            result = await agent.run_once()

        assert result["status"] == "failed"
        assert result["fetched_count"] == 5
        assert result["pushed"] is False
        assert len(result["errors"]) > 0
        assert any("push" in e for e in result["errors"])


# ===================================================================
# 6. Lock conflict path
# ===================================================================


class TestLockConflict:
    """When the asyncio.Lock is already held, run_once returns 'skipped'."""

    @pytest.mark.asyncio
    async def test_concurrent_call_skipped(self):
        from app.agents.news_agent import NewsAgent

        config = _make_config()
        agent = NewsAgent(config)

        # Simulate a concurrent call holding the lock
        await agent._lock.acquire()
        try:
            result = await agent.run_once()
        finally:
            agent._lock.release()

        assert result["status"] == "skipped"
        assert result["fetched_count"] == 0
        assert result["pushed"] is False
        assert len(result["errors"]) > 0


# ===================================================================
# 7. Top 5 selection (delegated to pipeline)
# ===================================================================


class TestTop5Selection:
    """Verify that the agent correctly reports pipeline-selected counts.

    Note: actual scoring/ranking logic is now in Merger (tested in test_merger.py).
    """

    @pytest.mark.asyncio
    async def test_selected_count_reflects_pipeline_output(self):
        """Agent reports the selected_count from the pipeline result."""
        from app.agents.news_agent import NewsAgent

        config = _make_config()
        mock_result = _make_publish_result(selected_count=5)

        with patch(
            "app.pipeline.news_pipeline.run_pipeline",
            new=AsyncMock(return_value=mock_result),
        ):
            agent = NewsAgent(config)
            result = await agent.run_once()

        assert result["status"] == "ok"
        assert result["fetched_count"] == 5

    @pytest.mark.asyncio
    async def test_pipeline_with_fewer_than_5(self):
        """When pipeline selects fewer than 5, agent reports the actual count."""
        from app.agents.news_agent import NewsAgent

        config = _make_config()
        mock_result = _make_publish_result(selected_count=3)

        with patch(
            "app.pipeline.news_pipeline.run_pipeline",
            new=AsyncMock(return_value=mock_result),
        ):
            agent = NewsAgent(config)
            result = await agent.run_once()

        assert result["status"] == "ok"
        assert result["fetched_count"] == 3

    @pytest.mark.asyncio
    async def test_pipeline_run_context_is_passed(self):
        """The pipeline receives correct RunContext and config."""
        from app.agents.news_agent import NewsAgent

        config = _make_config()
        mock_result = _make_publish_result()

        with patch(
            "app.pipeline.news_pipeline.run_pipeline",
            new=AsyncMock(return_value=mock_result),
        ) as mock_pipeline:
            agent = NewsAgent(config)
            await agent.run_once()

        # Verify pipeline was called with context and config
        mock_pipeline.assert_called_once()
        call_args = mock_pipeline.call_args
        assert call_args[0][1] is config  # second arg is config


# ===================================================================
# 8. Links preserved in final output
# ===================================================================


class TestLinksPreserved:
    """Verify that the agent passes through summary_preview and handles results correctly."""

    @pytest.mark.asyncio
    async def test_summary_preview_is_passed_through(self):
        """summary_preview from pipeline is reflected in agent result."""
        from app.agents.news_agent import NewsAgent

        config = _make_config()
        preview = "# 今日 AI 新闻摘要\n有3条重要新闻"

        mock_result = _make_publish_result(
            summary_preview=preview,
            selected_count=3,
        )

        with patch(
            "app.pipeline.news_pipeline.run_pipeline",
            new=AsyncMock(return_value=mock_result),
        ):
            agent = NewsAgent(config)
            result = await agent.run_once()

        assert result["status"] == "ok"
        assert preview in result["summary_preview"]
        assert result["fetched_count"] == 3

    @pytest.mark.asyncio
    async def test_summary_preview_is_truncated(self):
        """summary_preview should be the first 200 characters of the summary."""
        from app.agents.news_agent import NewsAgent

        config = _make_config()
        long_summary = "A" * 500  # 500 chars — truncated to 200

        mock_result = _make_publish_result(
            summary_preview=long_summary[:200],
        )

        with patch(
            "app.pipeline.news_pipeline.run_pipeline",
            new=AsyncMock(return_value=mock_result),
        ):
            agent = NewsAgent(config)
            result = await agent.run_once()

        # Verify the preview is exactly 200 chars (pipeline's make_preview truncates)
        assert len(result["summary_preview"]) == 200

    @pytest.mark.asyncio
    async def test_pipeline_error_propagates_to_agent_result(self):
        """When pipeline returns errors, they appear in the agent result."""
        from app.agents.news_agent import NewsAgent

        config = _make_config()
        mock_result = _make_publish_result(
            status="failed",
            pushed=False,
            errors=["llm_parse: bad JSON", "push: rate limited"],
        )

        with patch(
            "app.pipeline.news_pipeline.run_pipeline",
            new=AsyncMock(return_value=mock_result),
        ):
            agent = NewsAgent(config)
            result = await agent.run_once()

        assert result["status"] == "failed"
        assert len(result["errors"]) == 2
        assert "llm_parse" in result["errors"][0]
        assert "push" in result["errors"][1]
