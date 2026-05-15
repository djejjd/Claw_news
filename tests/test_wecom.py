import time
import pytest
from pusher.wecom import WeComPusher, format_message, strip_html, CATEGORY_LABELS, CATEGORY_EMOJI
from collectors.base import HotItem


def make_item(title, url, summary, source, category, score, **kwargs):
    return HotItem(title, url, summary, source, category, score, time.time(), **kwargs)


class TestStripHtml:
    def test_removes_tags(self):
        assert strip_html("<p>Hello <b>World</b></p>") == "Hello World"

    def test_preserves_plain_text(self):
        assert strip_html("plain text") == "plain text"


class TestFormatMessage:
    def test_period_morning(self):
        items = [make_item("Test", "https://x.com/1", "summary", "qbitai", "ai", 5.0)]
        msg = format_message(items, "ai", period="morning")
        assert "早报" in msg

    def test_period_evening(self):
        items = [make_item("Test", "https://x.com/1", "summary", "qbitai", "ai", 5.0)]
        msg = format_message(items, "ai", period="evening")
        assert "晚报" in msg

    def test_en_marker(self):
        item = make_item("Paper", "https://x.com/1", "s", source="huggingface", category="ai", score=5.0)
        msg = format_message([item], "ai")
        assert "[EN]" in msg

    def test_xin_marker(self):
        item = make_item("New", "https://x.com/new", "s", source="qbitai", category="ai", score=5.0)
        msg = format_message([item], "ai", pushed_urls=set())
        assert "[新]" in msg

    def test_xu_marker(self):
        item = make_item("Old", "https://x.com/old", "s", source="qbitai", category="ai", score=5.0)
        msg = format_message([item], "ai", pushed_urls={"https://x.com/old"})
        assert "[续]" in msg

    def test_source_label(self):
        item = make_item("t", "https://x.com/t", "s", source="qbitai", category="ai", score=5.0)
        msg = format_message([item], "ai")
        assert "— 量子位" in msg

    def test_hf_source_label(self):
        item = make_item("t", "https://x.com/t", "s", source="huggingface", category="ai", score=5.0)
        msg = format_message([item], "ai")
        assert "— HuggingFace" in msg
        assert "[EN]" in msg

    def test_empty_items(self):
        msg = format_message([], "game")
        assert msg != ""

    def test_category_labels(self):
        assert CATEGORY_LABELS["ai"] == "AI 热点"
        assert CATEGORY_LABELS["game"] == "游戏热点"
        assert CATEGORY_LABELS["device"] == "数码硬件"

    def test_domestic_source_has_region_label(self):
        item = make_item("t", "https://x.com/t", "s", source="qbitai", category="ai", score=5.0)
        msg = format_message([item], "ai")
        assert "— 量子位 · 国内" in msg

    def test_foreign_source_has_region_label(self):
        item = make_item("t", "https://x.com/t", "s", source="huggingface", category="ai", score=5.0)
        msg = format_message([item], "ai")
        assert "— HuggingFace · 国外" in msg


class TestWeComPusher:
    @pytest.mark.asyncio
    async def test_push_sends_post(self, httpx_mock):
        webhook = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test"
        httpx_mock.add_response(url=webhook, json={"errcode": 0, "errmsg": "ok"})

        pusher = WeComPusher(webhook)
        items = {
            "ai": [make_item("AI Test", "https://x.com/ai", "summary", source="qbitai", category="ai", score=8.0)],
            "game": [],
            "device": [],
        }
        await pusher.push(items)
        assert len(httpx_mock.get_requests()) >= 1

    @pytest.mark.asyncio
    async def test_push_skips_empty_category(self, httpx_mock):
        webhook = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test"
        pusher = WeComPusher(webhook)
        items = {"ai": [], "game": [], "device": []}
        await pusher.push(items)
        assert len(httpx_mock.get_requests()) == 0

    @pytest.mark.asyncio
    async def test_push_with_period(self, httpx_mock):
        webhook = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test"
        httpx_mock.add_response(url=webhook, json={"errcode": 0, "errmsg": "ok"})

        pusher = WeComPusher(webhook)
        items = {
            "ai": [make_item("AI Test", "https://x.com/ai", "summary", source="qbitai", category="ai", score=8.0)],
            "game": [],
            "device": [],
        }
        await pusher.push(items, period="evening")
        assert len(httpx_mock.get_requests()) >= 1
