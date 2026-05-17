"""Tests for app/agents/news_agent.py — NewsAgent orchestration layer.

Covers:
- Full pipeline success (crawl -> score -> summarize -> push)
- No news path (empty items -> skipped)
- Crawl failure path (error -> error summary pushed)
- LLM failure path (error -> error summary pushed)
- Push failure path (push error -> failed status)
- Lock conflict (concurrent call -> skipped)
- Top 5 selection (10 candidates -> score/sort -> top 5)
- Links preserved in final output
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.config import AppConfig

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


def _make_items(count: int = 5, *, pub_date: str = "2026-05-17") -> list[dict]:
    """Return fake news items matching fetch_news output format."""
    return [
        {
            "title": f"AI 新闻标题 {i}",
            "link": f"https://example.com/news/{i}",
            "summary": f"这是第 {i} 条 AI 新闻摘要",
            "published_at": pub_date,
        }
        for i in range(count)
    ]


SUMMARY = (
    "今日 AI 新闻摘要\n\n"
    "1. [AI新闻标题 0](https://example.com/news/0)\n"
    "   - 核心内容：测试摘要\n"
    "   - 重要性：高\n"
    "   - 趋势判断：利好\n\n"
    "今日一句话判断：AI行业持续发展"
)


# ===================================================================
# 1. Successful full pipeline
# ===================================================================


class TestNewsAgentSuccess:
    """Happy path: crawl -> score -> summarize -> push all succeed."""

    @pytest.mark.asyncio
    async def test_full_pipeline_ok(self):
        from app.agents.news_agent import NewsAgent

        config = _make_config()
        items = _make_items(8)

        with (
            patch(
                "app.agents.news_agent.fetch_news", new=AsyncMock(return_value=items)
            ) as mock_fetch,
            patch(
                "app.agents.news_agent.summarize_news",
                new=AsyncMock(return_value=SUMMARY),
            ) as mock_llm,
            patch(
                "app.agents.news_agent.send_text",
                new=AsyncMock(return_value={"errcode": 0, "errmsg": "ok"}),
            ) as mock_push,
        ):
            agent = NewsAgent(config)
            result = await agent.run_once()

        assert result["status"] == "ok"
        assert result["fetched_count"] == 8
        assert result["pushed"] is True
        assert SUMMARY in result["summary_preview"]
        assert result["errors"] == []

        mock_fetch.assert_called_once_with(config.news_rss_urls, limit=10)
        mock_llm.assert_called_once()
        mock_push.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_receives_top_5_items(self):
        """When 8 items are fetched, LLM receives exactly 5 after scoring."""
        from app.agents.news_agent import NewsAgent

        config = _make_config()
        items = _make_items(8)

        with (
            patch("app.agents.news_agent.fetch_news", new=AsyncMock(return_value=items)),
            patch(
                "app.agents.news_agent.summarize_news",
                new=AsyncMock(return_value=SUMMARY),
            ) as mock_llm,
            patch(
                "app.agents.news_agent.send_text",
                new=AsyncMock(return_value={"errcode": 0, "errmsg": "ok"}),
            ),
        ):
            agent = NewsAgent(config)
            await agent.run_once()

        call_args = mock_llm.call_args
        items_sent_to_llm = call_args[0][0]
        assert len(items_sent_to_llm) == 5


# ===================================================================
# 2. No news path
# ===================================================================


class TestNoNews:
    """When fetch_news returns no items, pipeline should stop early."""

    @pytest.mark.asyncio
    async def test_no_items_skips_pipeline(self):
        from app.agents.news_agent import NewsAgent

        config = _make_config()

        with (
            patch(
                "app.agents.news_agent.fetch_news", new=AsyncMock(return_value=[])
            ) as mock_fetch,
            patch("app.agents.news_agent.summarize_news") as mock_llm,
            patch("app.agents.news_agent.send_text") as mock_push,
        ):
            agent = NewsAgent(config)
            result = await agent.run_once()

        assert result["status"] == "skipped"
        assert result["fetched_count"] == 0
        assert result["pushed"] is False
        assert result["summary_preview"] == ""
        assert result["errors"] == []

        mock_fetch.assert_called_once()
        mock_llm.assert_not_called()
        mock_push.assert_not_called()


# ===================================================================
# 3. Crawl failure path
# ===================================================================


class TestCrawlFailure:
    """When fetch_news raises, error is logged and error summary pushed."""

    @pytest.mark.asyncio
    async def test_crawl_error_pushes_error_summary(self, caplog):
        from app.agents.news_agent import NewsAgent

        config = _make_config()

        with (
            patch(
                "app.agents.news_agent.fetch_news",
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
        assert any("crawl" in e for e in result["errors"])

        # Verify error was pushed
        mock_push.assert_called_once()
        call_args = mock_push.call_args
        pushed_content = call_args[0][1]
        assert "RSS feed down" in pushed_content or "运行异常" in pushed_content

        # Verify error was logged
        assert any(
            "抓取失败" in r.message or "RSS feed down" in r.message
            for r in caplog.records
            if r.levelname in ("ERROR", "WARNING")
        )


# ===================================================================
# 4. LLM failure path
# ===================================================================


class TestLLMFailure:
    """When LLM summarization fails, error is logged and error summary pushed."""

    @pytest.mark.asyncio
    async def test_llm_error_pushes_error_summary(self):
        from app.agents.news_agent import NewsAgent

        config = _make_config()
        items = _make_items(5)

        with (
            patch("app.agents.news_agent.fetch_news", new=AsyncMock(return_value=items)),
            patch(
                "app.agents.news_agent.summarize_news",
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
        assert result["fetched_count"] == 5
        assert result["pushed"] is True  # error summary was pushed
        assert len(result["errors"]) > 0
        assert any("llm" in e for e in result["errors"])

        # Verify error was pushed
        mock_push.assert_called_once()
        call_args = mock_push.call_args
        pushed_content = call_args[0][1]
        assert "LLM" in pushed_content or "运行异常" in pushed_content

    @pytest.mark.asyncio
    async def test_llm_error_does_not_attempt_primary_push(self):
        """After LLM fails, the primary summary is never pushed — only the error."""
        from app.agents.news_agent import NewsAgent

        config = _make_config()
        items = _make_items(5)

        with (
            patch("app.agents.news_agent.fetch_news", new=AsyncMock(return_value=items)),
            patch(
                "app.agents.news_agent.summarize_news",
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
        items = _make_items(5)

        with (
            patch("app.agents.news_agent.fetch_news", new=AsyncMock(return_value=items)),
            patch(
                "app.agents.news_agent.summarize_news",
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
        assert result["errors"] == ["llm: SilentLLMError"]


# ===================================================================
# 5. Push failure path
# ===================================================================


class TestPushFailure:
    """When the WeCom push itself fails, the result reports 'failed'."""

    @pytest.mark.asyncio
    async def test_push_failure_returns_failed(self):
        from app.agents.news_agent import NewsAgent
        from app.tools.wecom import WeComError

        config = _make_config()
        items = _make_items(5)

        with (
            patch("app.agents.news_agent.fetch_news", new=AsyncMock(return_value=items)),
            patch(
                "app.agents.news_agent.summarize_news",
                new=AsyncMock(return_value=SUMMARY),
            ),
            patch(
                "app.agents.news_agent.send_text",
                side_effect=WeComError(errcode=45009, errmsg="api freq out of limit"),
            ),
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
# 7. Top 5 selection (10 candidates -> score/sort -> top 5)
# ===================================================================


class TestTop5Selection:
    """Verify that only the top-5 scoring items are passed to the LLM."""

    @pytest.mark.asyncio
    async def test_recent_items_ranked_higher_than_old(self):
        """Recent items (today) score higher due to time_modifier = 0 vs -2.0 for old."""
        from app.agents.news_agent import NewsAgent

        config = _make_config()

        # Build 10 items: 5 recent (today), 5 old (months ago)
        items: list[dict] = []
        for i in range(5):
            items.append(
                {
                    "title": f"Recent 新闻 {i}",
                    "link": f"https://example.com/recent/{i}",
                    "summary": f"Recent summary {i}",
                    "published_at": "2026-05-17",  # today -> time_modifier=0
                }
            )
        for i in range(5):
            items.append(
                {
                    "title": f"Old 新闻 {i}",
                    "link": f"https://example.com/old/{i}",
                    "summary": f"Old summary {i}",
                    "published_at": "2026-01-01",  # old -> time_modifier=-2.0
                }
            )

        with (
            patch("app.agents.news_agent.fetch_news", new=AsyncMock(return_value=items)),
            patch(
                "app.agents.news_agent.summarize_news",
                new=AsyncMock(return_value=SUMMARY),
            ) as mock_llm,
            patch(
                "app.agents.news_agent.send_text",
                new=AsyncMock(return_value={"errcode": 0, "errmsg": "ok"}),
            ),
        ):
            agent = NewsAgent(config)
            result = await agent.run_once()

        assert result["status"] == "ok"
        assert result["fetched_count"] == 10

        # LLM should receive exactly 5 items
        call_args = mock_llm.call_args
        items_for_llm = call_args[0][0]
        assert len(items_for_llm) == 5

        # All 5 should be recent (higher score)
        for item in items_for_llm:
            assert "Recent" in item["title"]

    @pytest.mark.asyncio
    async def test_position_affects_sorting(self):
        """Items earlier in the feed (lower position) get higher position_score."""
        from app.agents.news_agent import NewsAgent

        config = _make_config()

        # Two items, same date, but first has better position
        items = [
            {
                "title": "First item (pos 1)",
                "link": "https://example.com/1",
                "summary": "First",
                "published_at": "2026-05-17",
            },
            {
                "title": "Second item (pos 2)",
                "link": "https://example.com/2",
                "summary": "Second",
                "published_at": "2026-05-17",
            },
        ]

        with (
            patch("app.agents.news_agent.fetch_news", new=AsyncMock(return_value=items)),
            patch(
                "app.agents.news_agent.summarize_news",
                new=AsyncMock(return_value=SUMMARY),
            ) as mock_llm,
            patch(
                "app.agents.news_agent.send_text",
                new=AsyncMock(return_value={"errcode": 0, "errmsg": "ok"}),
            ),
        ):
            agent = NewsAgent(config)
            await agent.run_once()

        call_args = mock_llm.call_args
        items_for_llm = call_args[0][0]
        # First positional item should appear first in the sorted list
        assert items_for_llm[0]["title"] == "First item (pos 1)"

    @pytest.mark.asyncio
    async def test_less_than_5_items_all_passed(self):
        """When fewer than 5 items are fetched, all are passed to LLM."""
        from app.agents.news_agent import NewsAgent

        config = _make_config()
        items = _make_items(3)

        with (
            patch("app.agents.news_agent.fetch_news", new=AsyncMock(return_value=items)),
            patch(
                "app.agents.news_agent.summarize_news",
                new=AsyncMock(return_value=SUMMARY),
            ) as mock_llm,
            patch(
                "app.agents.news_agent.send_text",
                new=AsyncMock(return_value={"errcode": 0, "errmsg": "ok"}),
            ),
        ):
            agent = NewsAgent(config)
            result = await agent.run_once()

        assert result["status"] == "ok"
        call_args = mock_llm.call_args
        items_for_llm = call_args[0][0]
        assert len(items_for_llm) == 3


# ===================================================================
# 8. Links preserved in final output
# ===================================================================


class TestLinksPreserved:
    """Verify that the final pushed content contains original article links."""

    @pytest.mark.asyncio
    async def test_pushed_content_contains_original_links(self):
        from app.agents.news_agent import NewsAgent

        config = _make_config()
        items = _make_items(3)

        summary_with_links = (
            "今日 AI 新闻摘要\n\n"
            "1. [AI新闻标题 0](https://example.com/news/0)\n"
            "   - 核心内容：摘要内容\n"
            "   - 重要性：高\n"
            "   - 趋势判断：利好\n\n"
            "2. [AI新闻标题 1](https://example.com/news/1)\n"
            "   - 核心内容：摘要内容\n"
            "   - 重要性：中\n"
            "   - 趋势判断：中性\n\n"
            "今日一句话判断：AI行业稳步前进"
        )

        with (
            patch("app.agents.news_agent.fetch_news", new=AsyncMock(return_value=items)),
            patch(
                "app.agents.news_agent.summarize_news",
                new=AsyncMock(return_value=summary_with_links),
            ),
            patch(
                "app.agents.news_agent.send_text",
                new=AsyncMock(return_value={"errcode": 0, "errmsg": "ok"}),
            ) as mock_push,
        ):
            agent = NewsAgent(config)
            result = await agent.run_once()

        assert result["status"] == "ok"

        # Verify the pushed content contains the original links
        call_args = mock_push.call_args
        pushed_content = call_args[0][1]
        assert "https://example.com/news/0" in pushed_content
        assert "https://example.com/news/1" in pushed_content

    @pytest.mark.asyncio
    async def test_summary_preview_is_truncated(self):
        """summary_preview should be the first 200 characters of the summary."""
        from app.agents.news_agent import NewsAgent

        config = _make_config()
        items = _make_items(3)

        long_summary = "A" * 500  # 500 chars

        with (
            patch("app.agents.news_agent.fetch_news", new=AsyncMock(return_value=items)),
            patch(
                "app.agents.news_agent.summarize_news",
                new=AsyncMock(return_value=long_summary),
            ),
            patch(
                "app.agents.news_agent.send_text",
                new=AsyncMock(return_value={"errcode": 0, "errmsg": "ok"}),
            ),
        ):
            agent = NewsAgent(config)
            result = await agent.run_once()

        assert len(result["summary_preview"]) == 200
        assert result["summary_preview"] == long_summary[:200]
