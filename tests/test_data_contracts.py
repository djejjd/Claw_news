"""Phase 0: Data contract verification tests."""

import pytest

from app.pipeline import (
    DigestPayload,
    PublishResult,
    SummaryItem,
    SummaryResult,
)
from app.pipeline.candidate import CandidateItem
from app.pipeline.context import RunContext
from collectors.base import HotItem, hotitem_to_candidate


class TestCandidateItem:
    """Tests for CandidateItem.make_canonical_key and construction."""

    def test_make_canonical_key_strips_query_string(self):
        result = CandidateItem.make_canonical_key("https://example.com/path/to/article?utm=xxx")
        assert result == "example.com/path/to/article"

    def test_make_canonical_key_basic_url(self):
        result = CandidateItem.make_canonical_key("https://qbitai.com/article/12345")
        assert result == "qbitai.com/article/12345"

    def test_make_canonical_key_strips_fragment(self):
        result = CandidateItem.make_canonical_key("https://example.com/news#section")
        assert result == "example.com/news"

    def test_make_canonical_key_strips_both_query_and_fragment(self):
        result = CandidateItem.make_canonical_key(
            "https://example.com/path/to/article?utm=xxx#section"
        )
        assert result == "example.com/path/to/article"

    def test_make_canonical_key_no_path(self):
        result = CandidateItem.make_canonical_key("https://example.com")
        assert result == "example.com"


class TestHotItemToCandidate:
    """Tests for HotItem → CandidateItem conversion."""

    def test_basic_conversion(self):
        hot = HotItem(
            title="Test Article",
            url="https://qbitai.com/article/12345",
            summary="A test summary",
            source="qbitai",
            category="ai",
            source_score=7.5,
            timestamp=1716000000.0,
            keyword_hit=True,
            pub_date="2024-05-18",
        )
        candidate = hotitem_to_candidate(hot, ingest_run_id="run-001")

        assert isinstance(candidate, CandidateItem)
        assert candidate.title == "Test Article"
        assert candidate.url == "https://qbitai.com/article/12345"
        assert candidate.summary == "A test summary"
        assert candidate.source == "qbitai"
        assert candidate.category == "ai"
        assert candidate.published_at == "2024-05-18"
        assert candidate.fetched_at != ""
        assert candidate.canonical_key == "qbitai.com/article/12345"
        assert candidate.ingest_run_id == "run-001"

    def test_conversion_empty_url(self):
        hot = HotItem(
            title="No URL",
            url="",
            summary="",
            source="test",
            category="ai",
            source_score=1.0,
            timestamp=1716000000.0,
            keyword_hit=False,
            pub_date="",
        )
        candidate = hotitem_to_candidate(hot)

        assert candidate.url == ""
        assert candidate.canonical_key == ""

    def test_conversion_default_ingest_run_id(self):
        hot = HotItem(
            title="T",
            url="https://example.com",
            summary="",
            source="t",
            category="ai",
            source_score=1.0,
            timestamp=1716000000.0,
            keyword_hit=False,
            pub_date="",
        )
        candidate = hotitem_to_candidate(hot)
        assert candidate.ingest_run_id == ""

    def test_device_alias_normalizes_to_tool(self):
        hot = HotItem(
            title="Tool Alias",
            url="https://example.com/tool",
            summary="",
            source="ithome",
            category="device",
            source_score=1.0,
            timestamp=1716000000.0,
            keyword_hit=False,
            pub_date="",
        )

        candidate = hotitem_to_candidate(hot)

        assert candidate.category == "tool"

    def test_conversion_hashed_url_keys_match(self):
        """Items with different query strings but same base URL get same canonical_key."""
        hot1 = HotItem(
            title="A",
            url="https://example.com/article?id=1&utm=src",
            summary="",
            source="t",
            category="ai",
            source_score=1.0,
            timestamp=1716000000.0,
            keyword_hit=False,
            pub_date="",
        )
        hot2 = HotItem(
            title="B",
            url="https://example.com/article?utm=other",
            summary="",
            source="t",
            category="ai",
            source_score=1.0,
            timestamp=1716000000.0,
            keyword_hit=False,
            pub_date="",
        )
        c1 = hotitem_to_candidate(hot1)
        c2 = hotitem_to_candidate(hot2)
        assert c1.canonical_key == c2.canonical_key
        assert c1.canonical_key == "example.com/article"


class TestRunContext:
    """Tests for RunContext construction and defaults."""

    def test_create_with_defaults(self):
        ctx = RunContext(trigger_mode="scheduler")
        assert ctx.trigger_mode == "scheduler"
        assert ctx.period == "morning"
        assert ctx.time_window_start == ""
        assert ctx.time_window_end == ""
        assert ctx.publish_scope == "ai_only"
        assert ctx.state_namespace == "ai_digest"

    def test_create_full(self):
        ctx = RunContext(
            trigger_mode="http",
            period="morning",
            time_window_start="2024-05-18T00:00:00",
            time_window_end="2024-05-18T08:00:00",
            publish_scope="ai_only",
            state_namespace="ai_digest",
        )
        assert ctx.time_window_start == "2024-05-18T00:00:00"
        assert ctx.time_window_end == "2024-05-18T08:00:00"

    def test_frozen_prevents_mutation(self):
        ctx = RunContext(trigger_mode="scheduler")
        with pytest.raises(Exception):
            ctx.trigger_mode = "http"  # type: ignore[misc]


class TestSummaryResultDataclasses:
    """Tests for SummaryItem, SummaryResult, PublishResult, DigestPayload."""

    def test_summary_item_creation(self):
        item = SummaryItem(
            title="Test",
            url="https://example.com",
            core_summary="Test summary",
            importance="高",
            trend="up",
        )
        assert item.importance == "高"

    def test_summary_result_default(self):
        result = SummaryResult(headline_items=[], daily_judgement="")
        assert result.headline_items == []
        assert result.daily_judgement == ""

    def test_publish_result_default_errors(self):
        pr = PublishResult(
            status="ok",
            selected_count=3,
            pushed=True,
            message_type="markdown",
            summary_preview="preview",
        )
        assert pr.errors == []

    def test_digest_payload_defaults(self):
        dp = DigestPayload(
            date="2024-05-18",
            period="morning",
            published_at="2024-05-18T08:00:00",
            trigger_mode="scheduler",
        )
        assert dp.headline_items == []
        assert dp.daily_judgement == ""
        assert dp.source_failures == []
        assert dp.published_urls == []
        assert dp.published_keys == []


class TestPipelineInitExports:
    """Verify all public interfaces are importable from app.pipeline."""

    def test_all_exports_importable(self):
        from app.pipeline import (
            CandidateItem,
            DigestPayload,
            PublishResult,
            RunContext,
            SummaryItem,
            SummaryResult,
        )

        # If we get here, all imports succeeded
        assert RunContext is not None
        assert CandidateItem is not None
        assert SummaryItem is not None
        assert SummaryResult is not None
        assert PublishResult is not None
        assert DigestPayload is not None
