"""Tests for run_pipeline — the unified news publishing pipeline.

These tests mock the pipeline's internal dependencies to verify core
behaviours: success, push failure, state persistence, and no-candidate skip.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import AppConfig
from app.pipeline.candidate import CandidateItem
from app.pipeline.context import RunContext

# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------

def _make_config(**kwargs) -> AppConfig:
    return AppConfig(
        llm_api_key="test-key",
        llm_base_url="https://api.example.com",
        llm_model="test-model",
        wecom_webhook_url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test",
        tz="Asia/Shanghai",
        news_rss_urls=[],
        **kwargs,
    )


def _make_candidate(
    title: str = "Test",
    url: str = "https://example.com/1",
    summary: str = "Summary",
    source: str = "qbitai",
    category: str = "ai",
    published_at: str = "2026-05-18",
) -> CandidateItem:
    return CandidateItem(
        title=title,
        url=url,
        summary=summary,
        source=source,
        category=category,
        published_at=published_at,
    )


def _make_ctx(**kwargs) -> RunContext:
    return RunContext(
        trigger_mode="cli_compat",
        time_window_start="2026-05-18T00:00:00",
        time_window_end="2026-05-18T12:00:00",
        **kwargs,
    )


def _make_llm_result() -> dict:
    return {
        "headline_items": [
            {
                "title": "Test News",
                "url": "https://example.com/1",
                "core_summary": "A test summary.",
                "importance": "高",
                "trend": "利好",
            }
        ],
        "daily_judgement": "AI行业稳步发展",
    }


def _make_push_result(*, success: bool = True) -> "PushResult":
    from pusher.wecom import PushResult

    return PushResult(
        category="ai",
        success=success,
        urls=["https://example.com/1"] if success else [],
        errcode=0 if success else 45009,
        errmsg="ok" if success else "rate limited",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPipelineSuccess:
    """Full pipeline success path — push succeeds, state is persisted."""

    @pytest.mark.asyncio
    async def test_run_pipeline_all_success(self, tmp_path: Path):
        """When all stages succeed, status is 'ok' and pushed is True."""
        from app.pipeline.news_pipeline import run_pipeline

        config = _make_config()
        ctx = _make_ctx()
        candidate = _make_candidate()
        llm_result = _make_llm_result()
        push_result = _make_push_result(success=True)

        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_is,
            patch("app.pipeline.news_pipeline.summarize_news", new=AsyncMock(return_value=llm_result)),
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_pusher_cls,
            patch("app.pipeline.news_pipeline.TopicClassifier") as mock_cls,
        ):
            # IngestionStore returns one candidate
            mock_is_inst = MagicMock()
            mock_is_inst.load_window_candidates.return_value = [candidate]
            mock_is.return_value = mock_is_inst

            # Topic classifier is a no-op
            mock_cls_inst = MagicMock()
            mock_cls.return_value = mock_cls_inst

            # WeCom push succeeds
            mock_pusher = MagicMock()
            mock_pusher.push_single_markdown = AsyncMock(return_value=push_result)
            mock_pusher_cls.return_value = mock_pusher

            result = await run_pipeline(ctx, config)

        assert result.status == "ok"
        assert result.pushed is True
        assert result.selected_count == 1
        assert result.errors == []


class TestPipelinePushFailure:
    """When the WeCom push fails, the pipeline reports failure."""

    @pytest.mark.asyncio
    async def test_push_failure_returns_failed(self, tmp_path: Path):
        """A push failure produces status='failed' with pushed=False and error details."""
        from app.pipeline.news_pipeline import run_pipeline

        config = _make_config()
        ctx = _make_ctx()
        candidate = _make_candidate()
        llm_result = _make_llm_result()
        push_result = _make_push_result(success=False)

        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_is,
            patch("app.pipeline.news_pipeline.summarize_news", new=AsyncMock(return_value=llm_result)),
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_pusher_cls,
            patch("app.pipeline.news_pipeline.TopicClassifier") as mock_cls,
        ):
            mock_is_inst = MagicMock()
            mock_is_inst.load_window_candidates.return_value = [candidate]
            mock_is.return_value = mock_is_inst

            mock_cls_inst = MagicMock()
            mock_cls.return_value = mock_cls_inst

            mock_pusher = MagicMock()
            mock_pusher.push_single_markdown = AsyncMock(return_value=push_result)
            mock_pusher_cls.return_value = mock_pusher

            result = await run_pipeline(ctx, config)

        assert result.status == "failed"
        assert result.pushed is False
        assert len(result.errors) > 0
        assert any("push" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_push_exception_returns_failed(self, tmp_path: Path):
        """An exception from the pusher is caught and reported as failure."""
        from app.pipeline.news_pipeline import run_pipeline

        config = _make_config()
        ctx = _make_ctx()
        candidate = _make_candidate()
        llm_result = _make_llm_result()

        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_is,
            patch("app.pipeline.news_pipeline.summarize_news", new=AsyncMock(return_value=llm_result)),
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_pusher_cls,
            patch("app.pipeline.news_pipeline.TopicClassifier") as mock_cls,
        ):
            mock_is_inst = MagicMock()
            mock_is_inst.load_window_candidates.return_value = [candidate]
            mock_is.return_value = mock_is_inst

            mock_cls_inst = MagicMock()
            mock_cls.return_value = mock_cls_inst

            # Pusher raises an exception
            mock_pusher = MagicMock()
            mock_pusher.push_single_markdown = AsyncMock(
                side_effect=RuntimeError("rate limited")
            )
            mock_pusher_cls.return_value = mock_pusher

            result = await run_pipeline(ctx, config)

        assert result.status == "failed"
        assert result.pushed is False
        assert len(result.errors) > 0


class TestPipelineNoCandidates:
    """When there are no candidates in the ingestion store, the pipeline skips."""

    @pytest.mark.asyncio
    async def test_no_candidates_returns_skipped(self, tmp_path: Path):
        """Empty candidate pool results in status='skipped'."""
        from app.pipeline.news_pipeline import run_pipeline

        config = _make_config()
        ctx = _make_ctx()

        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_is,
        ):
            mock_is_inst = MagicMock()
            mock_is_inst.load_window_candidates.return_value = []
            mock_is.return_value = mock_is_inst

            result = await run_pipeline(ctx, config)

        assert result.status == "skipped"
        assert result.selected_count == 0
        assert result.pushed is False


class TestPipelinePublishScope:
    """Formal publishing must obey the ai_only scope from RunContext."""

    @pytest.mark.asyncio
    async def test_ai_only_scope_excludes_non_ai_candidates(self, tmp_path: Path):
        from app.pipeline.news_pipeline import run_pipeline

        config = _make_config()
        ctx = _make_ctx()
        ai_candidate = _make_candidate(url="https://example.com/ai", category="ai")
        game_candidate = _make_candidate(url="https://example.com/game", category="game")
        llm_result = _make_llm_result()
        push_result = _make_push_result(success=True)

        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_is,
            patch(
                "app.pipeline.news_pipeline.summarize_news",
                new=AsyncMock(return_value=llm_result),
            ) as mock_llm,
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_pusher_cls,
            patch("app.pipeline.news_pipeline.TopicClassifier") as mock_cls,
        ):
            mock_is_inst = MagicMock()
            mock_is_inst.load_window_candidates.return_value = [ai_candidate, game_candidate]
            mock_is.return_value = mock_is_inst

            mock_cls_inst = MagicMock()
            mock_cls.return_value = mock_cls_inst

            mock_pusher = MagicMock()
            mock_pusher.push_single_markdown = AsyncMock(return_value=push_result)
            mock_pusher_cls.return_value = mock_pusher

            result = await run_pipeline(ctx, config)

        assert result.status == "ok"
        summarized_items = mock_llm.await_args.args[0]
        assert [item["link"] for item in summarized_items] == ["https://example.com/ai"]


class TestPipelineGitHubSupplement:
    @pytest.mark.asyncio
    async def test_github_items_rendered_but_not_sent_to_llm(self, tmp_path: Path):
        from app.pipeline.news_pipeline import run_pipeline
        from collectors.github import GitHubRepoItem

        config = _make_config()
        ctx = _make_ctx()
        candidate = _make_candidate(url="https://example.com/ai", category="ai")
        llm_result = _make_llm_result()
        push_result = _make_push_result(success=True)
        repos = [
            GitHubRepoItem(
                "owner/repo",
                "https://github.com/owner/repo",
                "desc",
                10,
                "Python",
                "2026-05-18T08:00:00",
            )
        ]

        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_is,
            patch("app.pipeline.news_pipeline.GitHubStore") as mock_github_store,
            patch(
                "app.pipeline.news_pipeline.summarize_news",
                new=AsyncMock(return_value=llm_result),
            ) as mock_llm,
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_pusher_cls,
            patch("app.pipeline.news_pipeline.TopicClassifier") as mock_cls,
        ):
            mock_is_inst = MagicMock()
            mock_is_inst.load_window_candidates.return_value = [candidate]
            mock_is.return_value = mock_is_inst
            mock_github_store.return_value.load_latest_snapshot.return_value = repos
            mock_cls.return_value = MagicMock()
            mock_pusher = MagicMock()
            mock_pusher.push_single_markdown = AsyncMock(return_value=push_result)
            mock_pusher_cls.return_value = mock_pusher

            result = await run_pipeline(ctx, config)

        assert result.status == "ok"
        assert mock_llm.await_args.args[0] == [
            {
                "title": "Test",
                "link": "https://example.com/ai",
                "summary": "Summary",
                "published_at": "2026-05-18",
            }
        ]
        pushed_markdown = mock_pusher.push_single_markdown.await_args.args[0]
        assert "今日值得看项目" in pushed_markdown
        assert "owner/repo" in pushed_markdown
