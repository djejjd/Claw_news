"""测试采集器失败容错：服务器部署时部分源不可用不应中断整体管道"""

import asyncio
import time
from datetime import date

import pytest

from aggregator.merger import Merger
from collectors.base import HotItem
from collectors.utils import safe_collect

# --- 模拟失败的采集器 ---


class FailingCollector:
    """模拟服务器端 HTTP 405 反爬拦截或网络不可达"""

    def __init__(self, exc=None):
        self._exc = exc or RuntimeError("HTTP 405 Not Allowed")

    async def collect(self):
        raise self._exc


class EmptyCollector:
    """模拟采集器正常返回但无数据（目标网站改版导致选择器失效）"""

    async def collect(self):
        return []


class MockCollector:
    """模拟正常采集"""

    def __init__(self, items):
        self._items = items

    async def collect(self):
        return self._items


class TestSafeCollect:
    """采集器容错：异常时返回空列表、不中断"""

    @pytest.mark.asyncio
    async def test_failing_collector_returns_empty(self, caplog):
        collector = FailingCollector()
        items = await safe_collect("failing", collector)
        assert items == []
        assert "采集失败" in caplog.text
        assert "405" in caplog.text

    @pytest.mark.asyncio
    async def test_empty_collector_returns_empty(self):
        collector = EmptyCollector()
        items = await safe_collect("empty", collector)
        assert items == []

    @pytest.mark.asyncio
    async def test_mixed_success_and_failure(self):
        """一个源失败不影响其他源的数据"""
        good = MockCollector([HotItem("t", "", "", "rss", "ai", 5.0)])
        bad = FailingCollector()

        good_items, bad_items = await asyncio.gather(
            safe_collect("good", good),
            safe_collect("bad", bad),
        )
        assert len(good_items) == 1
        assert bad_items == []

    @pytest.mark.asyncio
    async def test_all_failures_returns_empty_and_completes(self):
        """全部源失败时管道正常完成，不抛异常"""
        results = await asyncio.gather(
            safe_collect("a", FailingCollector()),
            safe_collect("b", FailingCollector()),
            safe_collect("c", FailingCollector()),
        )
        assert results == [[], [], []]


class TestMergerWithPartialFailure:
    """当一个源完全失败时，合并器仍正常工作"""

    def test_single_source_after_partner_fails(self):
        """TapTap 失败 → 游戏分类只剩游研社，仍应输出结果"""
        today = date.today().isoformat()
        items = [
            HotItem(
                "主机游戏评测",
                "https://y.com/1",
                "评测",
                "yystv",
                "game",
                8.0,
                time.time(),
                True,
                today,
            ),
            HotItem(
                "Steam 新游",
                "https://y.com/2",
                "新游",
                "yystv",
                "game",
                7.0,
                time.time(),
                True,
                today,
            ),
            HotItem(
                "手游攻略",
                "https://y.com/3",
                "攻略",
                "yystv",
                "game",
                6.0,
                time.time(),
                False,
                today,
            ),
            HotItem(
                "版本更新",
                "https://y.com/4",
                "更新",
                "yystv",
                "game",
                5.0,
                time.time(),
                False,
                today,
            ),
            HotItem(
                "赛季活动",
                "https://y.com/5",
                "活动",
                "yystv",
                "game",
                4.0,
                time.time(),
                False,
                today,
            ),
        ]
        merger = Merger(top_n=5)
        result = merger.merge(items, period="morning")
        assert len(result["game"]) == 5
        assert all(item.source == "yystv" for item in result["game"])

    def test_mixed_partial_and_full_sources(self):
        """AI: qbitai 成功 + HF 失败，不影响管道"""
        today = date.today().isoformat()
        items = [
            HotItem("AI 1", "https://q.com/1", "", "qbitai", "ai", 9.0, time.time(), True, today),
            HotItem("AI 2", "https://q.com/2", "", "qbitai", "ai", 8.5, time.time(), True, today),
            HotItem("AI 3", "https://q.com/3", "", "qbitai", "ai", 8.0, time.time(), True, today),
            HotItem("AI 4", "https://q.com/4", "", "qbitai", "ai", 7.5, time.time(), False, today),
            HotItem("AI 5", "https://q.com/5", "", "qbitai", "ai", 7.0, time.time(), False, today),
        ]
        merger = Merger(top_n=5)
        result = merger.merge(items, period="morning")
        assert len(result["ai"]) == 5

    def test_category_with_zero_items(self):
        """某个分类完全没有数据时，该分类返回空"""
        items = [
            HotItem(
                "AI Only",
                "https://a.com/1",
                "",
                "qbitai",
                "ai",
                5.0,
                time.time(),
                False,
                date.today().isoformat(),
            ),
        ]
        merger = Merger(top_n=5)
        result = merger.merge(items, period="morning")
        assert len(result["ai"]) == 1
        assert result["game"] == []
        assert result["device"] == []


class TestHTTPErrorPropagation:
    """各种 HTTP/网络错误应被 safe_collect 捕获并记录"""

    @pytest.mark.asyncio
    async def test_http_403_is_caught(self, caplog):
        collector = FailingCollector(RuntimeError("403 Forbidden"))
        items = await safe_collect("blocked", collector)
        assert items == []
        assert "403" in caplog.text

    @pytest.mark.asyncio
    async def test_connection_error_is_caught(self, caplog):
        collector = FailingCollector(ConnectionRefusedError("Connection refused"))
        items = await safe_collect("offline", collector)
        assert items == []
        assert "Connection refused" in caplog.text

    @pytest.mark.asyncio
    async def test_unexpected_exception_is_caught(self, caplog):
        collector = FailingCollector(ValueError("unexpected parsing failure"))
        items = await safe_collect("weird", collector)
        assert items == []
        assert "parsing failure" in caplog.text

    @pytest.mark.asyncio
    async def test_http_timeout_is_caught(self, caplog):
        collector = FailingCollector(TimeoutError("timed out"))
        items = await safe_collect("slow", collector)
        assert items == []
        assert "timed out" in caplog.text
