import time
import pytest
from pusher.wecom import WeComPusher, format_message, CATEGORY_LABELS, CATEGORY_EMOJI
from collectors.base import HotItem


def make_item(title, url, summary, category, score):
    return HotItem(title, url, summary, f"test-{category}", category, score, time.time())


class TestFormatMessage:
    def test_single_item(self):
        items = [make_item("Test Title", "https://x.com/1", "A short summary", "ai", 8.0)]
        msg = format_message(items, "ai")
        assert "AI" in msg
        assert "Test Title" in msg
        assert "https://x.com/1" in msg
        assert "A short summary" in msg
        assert "[Test Title](https://x.com/1)" in msg

    def test_empty_items(self):
        msg = format_message([], "game")
        assert msg != ""

    def test_category_labels(self):
        assert CATEGORY_LABELS["ai"] == "AI 热点"
        assert CATEGORY_LABELS["game"] == "游戏热点"
        assert CATEGORY_LABELS["device"] == "数码硬件"


class TestWeComPusher:
    @pytest.mark.asyncio
    async def test_push_sends_post(self, httpx_mock):
        """Verify POST is sent to webhook URL"""
        webhook = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test"
        httpx_mock.add_response(url=webhook, json={"errcode": 0, "errmsg": "ok"})

        pusher = WeComPusher(webhook)
        items = {
            "ai": [make_item("AI Test", "https://x.com/ai", "summary", "ai", 8.0)],
            "game": [],
            "device": [],
        }
        await pusher.push(items)
        assert len(httpx_mock.get_requests()) >= 1

    @pytest.mark.asyncio
    async def test_push_skips_empty_category(self, httpx_mock):
        """Empty categories don't send messages"""
        webhook = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test"

        pusher = WeComPusher(webhook)
        items = {"ai": [], "game": [], "device": []}
        await pusher.push(items)
        assert len(httpx_mock.get_requests()) == 0
