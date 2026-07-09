"""Tests for app/pipeline/news_pipeline.py — contract verification (no integration mocks)."""

import inspect

# ===================================================================
# 1. RunContext 构造正确
# ===================================================================


class TestRunContextConstruction:
    def test_full_construction(self):
        from app.pipeline.context import RunContext

        ctx = RunContext(
            trigger_mode="scheduler",
            period="morning",
            time_window_start="2026-05-18T00:00:00",
            time_window_end="2026-05-18T08:00:00",
            publish_scope="ai_only",
            state_namespace="ai_digest",
        )
        assert ctx.trigger_mode == "scheduler"
        assert ctx.period == "morning"
        assert ctx.time_window_start == "2026-05-18T00:00:00"
        assert ctx.time_window_end == "2026-05-18T08:00:00"
        assert ctx.publish_scope == "ai_only"
        assert ctx.state_namespace == "ai_digest"

    def test_defaults(self):
        from app.pipeline.context import RunContext

        ctx = RunContext(trigger_mode="http")
        assert ctx.period == "morning"
        assert ctx.publish_scope == "ai_only"
        assert ctx.state_namespace == "ai_digest"
        assert ctx.time_window_start == ""
        assert ctx.time_window_end == ""

    def test_immutable(self):
        from dataclasses import FrozenInstanceError

        from app.pipeline.context import RunContext

        ctx = RunContext(trigger_mode="scheduler")
        try:
            ctx.trigger_mode = "http"
            raise AssertionError("RunContext should be frozen")
        except FrozenInstanceError:
            pass


# ===================================================================
# 2. PublishResult 各状态构造
# ===================================================================


class TestPublishResultConstruction:
    def test_ok_status(self):
        from app.tools.summary_result import PublishResult

        r = PublishResult(
            status="ok",
            selected_count=5,
            pushed=True,
            message_type="markdown",
            summary_preview="# 今日 AI 新闻摘要...",
        )
        assert r.status == "ok"
        assert r.selected_count == 5
        assert r.pushed is True
        assert r.message_type == "markdown"
        assert r.errors == []

    def test_skipped_status(self):
        from app.tools.summary_result import PublishResult

        r = PublishResult(
            status="skipped",
            selected_count=0,
            pushed=False,
            message_type="markdown",
            summary_preview="",
        )
        assert r.status == "skipped"
        assert r.selected_count == 0
        assert r.pushed is False
        assert r.errors == []

    def test_failed_status(self):
        from app.tools.summary_result import PublishResult

        r = PublishResult(
            status="failed",
            selected_count=3,
            pushed=False,
            message_type="markdown",
            summary_preview="",
            errors=["push: rate limit exceeded"],
        )
        assert r.status == "failed"
        assert r.pushed is False
        assert "push" in r.errors[0]

    def test_ok_with_state_write_failure(self):
        from app.tools.summary_result import PublishResult

        r = PublishResult(
            status="ok",
            selected_count=5,
            pushed=True,
            message_type="markdown",
            summary_preview="# 摘要...",
            errors=["state_write_failed"],
        )
        assert r.status == "ok"
        assert r.pushed is True
        assert len(r.errors) == 1
        assert r.errors[0] == "state_write_failed"

    def test_errors_defaults_to_empty_list(self):
        from app.tools.summary_result import PublishResult

        r = PublishResult(
            status="ok",
            selected_count=1,
            pushed=True,
            message_type="markdown",
            summary_preview="",
        )
        assert r.errors == []
        assert isinstance(r.errors, list)


# ===================================================================
# 3. DigestPayload 字段完整性
# ===================================================================


class TestDigestPayloadFields:
    def test_all_fields_populated(self):
        from app.tools.summary_result import DigestPayload

        d = DigestPayload(
            date="2026-05-18",
            period="morning",
            published_at="2026-05-18T08:00:00",
            trigger_mode="scheduler",
            headline_items=[
                {
                    "title": "GPT-5 Released",
                    "url": "https://example.com/1",
                    "core_summary": "OpenAI发布了GPT-5",
                    "importance": "高",
                    "trend": "模型能力继续提升",
                },
            ],
            daily_judgement="今日AI行业重大发布",
            source_failures=["qbitai_timeout", "huggingface_429"],
            published_urls=["https://example.com/1"],
            published_keys=["example.com/news/1"],
        )
        assert d.date == "2026-05-18"
        assert d.period == "morning"
        assert d.published_at == "2026-05-18T08:00:00"
        assert d.trigger_mode == "scheduler"
        assert len(d.headline_items) == 1
        assert d.headline_items[0]["title"] == "GPT-5 Released"
        assert d.daily_judgement == "今日AI行业重大发布"
        assert d.source_failures == ["qbitai_timeout", "huggingface_429"]
        assert d.published_urls == ["https://example.com/1"]
        assert d.published_keys == ["example.com/news/1"]

    def test_optional_fields_default_to_empty(self):
        from app.tools.summary_result import DigestPayload

        d = DigestPayload(
            date="2026-05-18",
            period="evening",
            published_at="",
            trigger_mode="manual",
        )
        assert d.headline_items == []
        assert d.daily_judgement == ""
        assert d.source_failures == []
        assert d.published_urls == []
        assert d.published_keys == []


# ===================================================================
# 4. pipeline 函数签名正确（import 验证）
# ===================================================================


class TestPipelineSignature:
    def test_run_pipeline_is_async_function(self):
        from app.pipeline.news_pipeline import run_pipeline

        assert inspect.iscoroutinefunction(run_pipeline)

    def test_run_pipeline_accepts_ctx_and_config(self):
        from app.pipeline.news_pipeline import run_pipeline

        sig = inspect.signature(run_pipeline)
        params = list(sig.parameters.keys())
        assert "ctx" in params
        assert "config" in params
        assert len(params) == 2

    def test_module_imports_without_side_effects(self):
        """Verify the module can be imported without triggering network calls."""
        from app.pipeline import news_pipeline

        assert hasattr(news_pipeline, "run_pipeline")
        assert hasattr(news_pipeline, "_collect_source_failures")

    def test_data_dir_is_data_directory(self):
        from app.pipeline.news_pipeline import _DATA_DIR

        assert _DATA_DIR.name == "data"
        assert _DATA_DIR.exists()


class TestMatchSelectedCandidate:
    def test_exact_url_match(self):
        from app.pipeline.news_pipeline import _match_selected_candidate
        from app.pipeline.candidate import CandidateItem
        selected = [CandidateItem(title="T", url="https://a.com/1", summary="", source="x", category="ai")]
        result = _match_selected_candidate(selected, {"url": "https://a.com/1"})
        assert result is not None
        assert result.url == "https://a.com/1"

    def test_exact_title_match(self):
        from app.pipeline.news_pipeline import _match_selected_candidate
        from app.pipeline.candidate import CandidateItem
        selected = [CandidateItem(title="Exact Title", url="https://a.com/1", summary="", source="x", category="ai")]
        result = _match_selected_candidate(selected, {"title": "Exact Title"})
        assert result is not None
        assert result.title == "Exact Title"

    def test_canonical_key_fallback(self):
        """When URL and title don't match exactly, canonical_key should still work."""
        from app.pipeline.news_pipeline import _match_selected_candidate
        from app.pipeline.candidate import CandidateItem
        ck = CandidateItem.make_canonical_key("https://a.com/article/123")
        selected = [CandidateItem(
            title="Some Title", url="https://a.com/article/123",
            summary="", source="x", category="ai", canonical_key=ck,
        )]
        # LLM returned the same URL but with query params or different scheme
        result = _match_selected_candidate(selected, {
            "url": "https://a.com/article/123?utm=xxx",
            "title": "Rewritten Title",
        })
        assert result is not None
        assert result.url == "https://a.com/article/123"

    def test_canonical_key_beats_title_match(self):
        """当两个候选标题相同时，canonical_key 匹配优先于 title 匹配，
        防止 LLM 改写 URL 后被同标题的另一个候选截走。"""
        from app.pipeline.news_pipeline import _match_selected_candidate
        from app.pipeline.candidate import CandidateItem
        ck_a = CandidateItem.make_canonical_key("https://a.com/article/456")
        selected = [
            CandidateItem(title="Same Title", url="https://a.com/article/123",
                          summary="", source="x", category="ai",
                          canonical_key=CandidateItem.make_canonical_key("https://a.com/article/123")),
            CandidateItem(title="Same Title", url="https://a.com/article/456",
                          summary="", source="y", category="tool", canonical_key=ck_a),
        ]
        # LLM 返回了 candidate 2 的 URL（带 query param），标题相同
        result = _match_selected_candidate(selected, {
            "url": "https://a.com/article/456?ref=rss",
            "title": "Same Title",
        })
        assert result is not None
        assert result.url == "https://a.com/article/456"
        assert result.source == "y"  # canonical_key 命中，不是被 title 截到第一个

    def test_no_match_returns_none(self):
        from app.pipeline.news_pipeline import _match_selected_candidate
        from app.pipeline.candidate import CandidateItem
        selected = [CandidateItem(title="A", url="https://x.com/1", summary="", source="x", category="ai")]
        result = _match_selected_candidate(selected, {
            "url": "https://unrelated.com/2",
            "title": "Unrelated",
        })
        assert result is None
