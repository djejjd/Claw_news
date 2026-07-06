"""Tests for app/renderers/wecom_markdown.py and pusher push_single_markdown."""

import json
import re

import httpx
import pytest

from app.renderers.wecom_markdown import make_preview, render_digest
from app.tools.summary_result import SummaryItem, SummaryResult
from pusher.wecom import PushResult, WeComError, WeComPusher

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def make_item(
    title="Test Article",
    url="https://example.com/article",
    core_summary="An interesting article about AI.",
    importance="高",
    trend="持续关注",
):
    return SummaryItem(
        title=title,
        url=url,
        core_summary=core_summary,
        importance=importance,
        trend=trend,
    )


def make_result(items=None, daily_judgement="今天 AI 领域动作频频。"):
    return SummaryResult(
        headline_items=items or [],
        daily_judgement=daily_judgement,
    )


# ---------------------------------------------------------------------------
# render_digest tests
# ---------------------------------------------------------------------------


class TestRenderDigestBasic:
    """Basic rendering: heading, single item, daily_judgement."""

    def test_heading_present(self):
        result = make_result([make_item()])
        md = render_digest(result)
        assert md.startswith("# 今日 AI 新闻摘要")

    def test_single_headline_numbering(self):
        result = make_result([make_item(title="GPT-5 发布")])
        md = render_digest(result)
        assert "**1.**" in md

    def test_contains_title(self):
        result = make_result([make_item(title="GPT-5 发布")])
        md = render_digest(result)
        assert "GPT-5 发布" in md

    def test_contains_core_summary(self):
        result = make_result([make_item(core_summary="OpenAI 推出新一代模型。")])
        md = render_digest(result)
        assert "> 核心内容：OpenAI 推出新一代模型。" in md

    def test_contains_importance(self):
        result = make_result([make_item(importance="高")])
        md = render_digest(result)
        assert "> 重要性：高" in md

    def test_contains_trend(self):
        result = make_result([make_item(trend="持续关注")])
        md = render_digest(result)
        assert "> 趋势判断：持续关注" in md

    def test_contains_daily_judgement(self):
        result = make_result([make_item()], daily_judgement="AI 行业今日波澜不惊。")
        md = render_digest(result)
        assert "> 今日一句话判断：AI 行业今日波澜不惊。" in md

    def test_no_daily_judgement(self):
        """When daily_judgement is empty, no judgement line should appear."""
        result = make_result([make_item()], daily_judgement="")
        md = render_digest(result)
        assert "今日一句话判断" not in md


class TestRenderDigestMultiple:
    """Rendering with multiple headline items."""

    def test_multiple_items_numbering(self):
        items = [
            make_item(title="Item A"),
            make_item(title="Item B"),
            make_item(title="Item C"),
        ]
        result = make_result(items)
        md = render_digest(result)
        assert "**1.**" in md
        assert "**2.**" in md
        assert "**3.**" in md
        assert "**4.**" not in md

    def test_multiple_items_all_shown(self):
        items = [
            make_item(title="Item A", core_summary="Summary A"),
            make_item(title="Item B", core_summary="Summary B"),
        ]
        result = make_result(items)
        md = render_digest(result)
        assert "Item A" in md
        assert "Item B" in md
        assert "Summary A" in md
        assert "Summary B" in md


class TestRenderDigestEmpty:
    """Rendering with empty headline_items."""

    def test_empty_headlines_renders_heading_only(self):
        result = make_result([], daily_judgement="今天静悄悄。")
        md = render_digest(result)
        assert "# 今日 AI 新闻摘要" in md
        assert "> 今日一句话判断：今天静悄悄。" in md

    def test_none_headlines_treated_as_empty(self):
        result = make_result(None, daily_judgement="无事发生。")
        md = render_digest(result)
        assert "# 今日 AI 新闻摘要" in md
        assert "> 今日一句话判断：无事发生。" in md
        # No numbered entries should appear
        assert "**1.**" not in md


class TestRenderDigestLinkFormat:
    """Verify hyperlink format and absence of bare URLs."""

    def test_markdown_link_syntax(self):
        result = make_result([make_item(title="AI News", url="https://example.com/ai")])
        md = render_digest(result)
        # Title should be in [title](url) format
        assert "[AI News](https://example.com/ai)" in md

    def test_no_bare_url_in_body(self):
        """The URL should only appear inside a markdown link, never bare."""
        result = make_result([make_item(url="https://example.com/special")])
        md = render_digest(result)
        # Remove the markdown link syntax then check no URL remains
        without_links = re.sub(r"\[.*?\]\(.*?\)", "[LINK]", md)
        assert "https://example.com/special" not in without_links

    def test_no_url_in_non_link_lines(self):
        """Core summary, importance, trend lines must not contain bare URLs."""
        result = make_result([make_item(url="https://x.com/test")])
        md = render_digest(result)
        lines = md.split("\n")
        for line in lines:
            # Skip lines that contain markdown links (the numbered entry line)
            if line.startswith("**") and "](" in line:
                continue
            # No bare http(s) URLs on other lines
            assert "http://" not in line, f"Bare URL found in line: {line!r}"
            assert "https://" not in line, f"Bare URL found in line: {line!r}"

    def test_item_without_url(self):
        """Item without URL should still render title without link syntax."""
        result = make_result([make_item(title="No Link", url="")])
        md = render_digest(result)
        assert "**1.** No Link" in md
        assert "](" not in md


class TestRenderDigestEscape:
    """Special character escaping in titles."""

    def test_asterisk_escaped(self):
        result = make_result([make_item(title="AI *breakthrough* today")])
        md = render_digest(result)
        assert "\\*breakthrough\\*" in md

    def test_underscore_escaped(self):
        result = make_result([make_item(title="ML_model_v2 released")])
        md = render_digest(result)
        assert "ML\\_model\\_v2" in md

    def test_square_brackets_escaped(self):
        result = make_result([make_item(title="[Breaking] News")])
        md = render_digest(result)
        assert "\\[Breaking\\]" in md

    def test_backtick_escaped(self):
        result = make_result([make_item(title="Using `torch.compile` for speed")])
        md = render_digest(result)
        assert "\\`torch.compile\\`" in md

    def test_backslash_escaped(self):
        result = make_result([make_item(title="Path\\to\\file")])
        md = render_digest(result)
        assert "Path\\\\to\\\\file" in md

    def test_combined_special_chars(self):
        result = make_result([make_item(title="*Important* [Update] on `model_v2` with \\path")])
        md = render_digest(result)
        assert "\\*Important\\*" in md
        assert "\\[Update\\]" in md
        assert "\\`model\\_v2\\`" in md


class TestMakePreview:
    """Preview truncation from render_digest output."""

    def test_preview_within_limit(self):
        result = make_result([make_item(title="Short")])
        md = render_digest(result)
        preview = make_preview(md, max_chars=200)
        assert len(preview) <= 200
        assert preview == md[:200]

    def test_preview_truncation(self):
        result = make_result([make_item(title="A" * 300)])
        md = render_digest(result)
        preview = make_preview(md, max_chars=50)
        assert len(preview) == 50
        assert preview == md[:50]

    def test_preview_default_max_chars(self):
        result = make_result([make_item(title="Test")])
        md = render_digest(result)
        preview = make_preview(md)
        assert len(preview) <= 200


# ---------------------------------------------------------------------------
# WeComPusher.push_single_markdown tests
# ---------------------------------------------------------------------------

WEBHOOK = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test-key"


class TestPushSingleMarkdown:
    """Tests for the new push_single_markdown method on WeComPusher."""

    @pytest.mark.asyncio
    async def test_sends_correct_msgtype(self, httpx_mock):
        """The payload should use msgtype=markdown with a markdown.content field."""
        httpx_mock.add_response(
            url=WEBHOOK,
            method="POST",
            json={"errcode": 0, "errmsg": "ok"},
        )

        pusher = WeComPusher(WEBHOOK)
        await pusher.push_single_markdown("# Test\n\nContent")

        request = httpx_mock.get_request()
        payload = json.loads(request.read())
        assert payload["msgtype"] == "markdown"
        assert "markdown" in payload
        assert payload["markdown"]["content"] == "# Test\n\nContent"

    @pytest.mark.asyncio
    async def test_returns_push_result_with_ai_digest_category(self, httpx_mock):
        """Successful call returns PushResult with category='ai_digest'."""
        httpx_mock.add_response(
            url=WEBHOOK,
            method="POST",
            json={"errcode": 0, "errmsg": "ok"},
        )

        pusher = WeComPusher(WEBHOOK)
        result = await pusher.push_single_markdown("# Digest")

        assert isinstance(result, PushResult)
        assert result.category == "ai_digest"
        assert result.success is True
        assert result.errcode == 0

    @pytest.mark.asyncio
    async def test_business_error_raises(self, httpx_mock):
        """Non-zero errcode should raise WeComError."""
        httpx_mock.add_response(
            url=WEBHOOK,
            method="POST",
            json={"errcode": 45009, "errmsg": "api freq out of limit"},
        )

        pusher = WeComPusher(WEBHOOK)
        with pytest.raises(WeComError, match="45009"):
            await pusher.push_single_markdown("# Rate limited")

    @pytest.mark.asyncio
    async def test_http_error_propagates(self, httpx_mock):
        """HTTP errors (e.g. 500) should propagate."""
        httpx_mock.add_response(
            url=WEBHOOK,
            method="POST",
            status_code=500,
        )

        pusher = WeComPusher(WEBHOOK)
        with pytest.raises(httpx.HTTPStatusError):
            await pusher.push_single_markdown("# Server error")

    @pytest.mark.asyncio
    async def test_timeout_propagates(self, httpx_mock):
        """Timeout should raise httpx.TimeoutException."""
        httpx_mock.add_exception(
            httpx.TimeoutException("timed out"),
            url=WEBHOOK,
        )

        pusher = WeComPusher(WEBHOOK)
        with pytest.raises(httpx.TimeoutException):
            await pusher.push_single_markdown("# Timeout test")

    @pytest.mark.asyncio
    async def test_injected_client_reused(self, httpx_mock):
        """When an injected client is used, it should NOT be closed by the pusher."""
        httpx_mock.add_response(
            url=WEBHOOK,
            method="POST",
            json={"errcode": 0, "errmsg": "ok"},
        )

        async with httpx.AsyncClient() as client:
            pusher = WeComPusher(WEBHOOK, client=client)
            result = await pusher.push_single_markdown("# Injected")
            assert result.success is True
            # Client should still be usable after the call
            assert not client.is_closed


def test_render_digest_with_github_supplement():
    from collectors.github import GitHubRepoItem

    result = SummaryResult(
        headline_items=[
            SummaryItem(
                title="News",
                url="https://example.com/news",
                core_summary="summary",
                importance="高",
                trend="up",
            )
        ],
        daily_judgement="steady",
    )
    repos = [
        GitHubRepoItem(
            "owner/a", "https://github.com/owner/a", "desc a", 10, "Python", "2026-05-18T08:00:00"
        ),
        GitHubRepoItem(
            "owner/b",
            "https://github.com/owner/b",
            "desc b",
            9,
            "TypeScript",
            "2026-05-18T08:00:00",
        ),
        GitHubRepoItem(
            "owner/c", "https://github.com/owner/c", "desc c", 8, "Go", "2026-05-18T08:00:00"
        ),
    ]

    markdown = render_digest(result, github_items=repos)

    assert "## 今日值得看项目" in markdown
    assert "[owner/a](https://github.com/owner/a)" in markdown
    assert "⭐ 10" in markdown
