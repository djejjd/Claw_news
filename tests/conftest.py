import time as _time
from datetime import date as _date
from datetime import timedelta

import pytest

from collectors.base import HotItem


@pytest.fixture
def sample_items():
    """V1-compatible sample data (for backward compat in wecom tests)"""
    now = _time.time()
    return [
        HotItem("AI Paper A", "https://a.com/1", "Summary A", "huggingface", "ai", 9.0, now - 3600),
        HotItem("AI News B", "https://b.com/2", "Summary B", "rss", "ai", 5.0, now - 7200),
        HotItem("AI Old News", "https://b.com/3", "Older AI item", "rss", "ai", 5.0, now - 100000),
        HotItem("Game News C", "https://c.com/3", "Summary C", "taptap", "game", 8.0, now - 1800),
        HotItem("Game News D", "https://d.com/4", "Summary D", "rss", "game", 5.0, now - 40000),
        HotItem(
            "Game Old News",
            "https://d.com/5",
            "Very old game item",
            "rss",
            "game",
            5.0,
            now - 200000,
        ),
        HotItem("Tool E", "https://e.com/5", "Summary E", "ithome", "tool", 7.0, now - 600),
        HotItem("Tool F", "https://f.com/6", "Summary F", "rss", "tool", 5.0, now - 50000),
        HotItem("AI Paper A dup", "https://a.com/1", "Dup", "rss", "ai", 3.0, now - 3600),
    ]


@pytest.fixture
def sample_items_v2():
    """V2 sample data: period-aware, keyword_hit, pub_date, distinct sources"""
    now = _time.time()
    today = _date.today().isoformat()
    yesterday = (_date.today() - timedelta(days=1)).isoformat()
    return [
        # AI: huggingface (scored by upvotes) + qbitai (RSS 3D scoring)
        HotItem(
            "AI Paper A",
            "https://a.com/1",
            "AI research",
            "huggingface",
            "ai",
            9.0,
            now - 3600,
            True,
            today,
        ),
        HotItem(
            "AI Paper B",
            "https://a.com/2",
            "ML paper",
            "huggingface",
            "ai",
            8.0,
            now - 3600,
            True,
            today,
        ),
        HotItem(
            "AI Paper C",
            "https://a.com/3",
            "DL paper",
            "huggingface",
            "ai",
            7.0,
            now - 3600,
            True,
            today,
        ),
        HotItem(
            "AI Paper D",
            "https://a.com/4",
            "CV paper",
            "huggingface",
            "ai",
            6.0,
            now - 3600,
            False,
            today,
        ),
        HotItem(
            "AI News 1", "https://b.com/1", "GPT news", "qbitai", "ai", 5.0, now - 7200, True, today
        ),
        HotItem(
            "AI News 2", "https://b.com/2", "AI news", "qbitai", "ai", 5.0, now - 7200, True, today
        ),
        # Game: taptap (rank scoring) + yystv (RSS 3D scoring)
        HotItem(
            "Game 1",
            "https://c.com/1",
            "New RPG 上线",
            "taptap",
            "game",
            9.0,
            now - 1800,
            True,
            today,
        ),
        HotItem(
            "Game 2",
            "https://c.com/2",
            "Strategy 手游",
            "taptap",
            "game",
            8.0,
            now - 1800,
            True,
            today,
        ),
        HotItem(
            "Game 3",
            "https://d.com/1",
            "主机 游戏 评测",
            "yystv",
            "game",
            5.0,
            now - 40000,
            True,
            yesterday,
        ),
        HotItem(
            "Game 4",
            "https://d.com/2",
            "Steam 新游",
            "yystv",
            "game",
            5.0,
            now - 40000,
            True,
            today,
        ),
        # Tool: ithome (RSS) + sspai (RSS)
        HotItem(
            "Tool 1",
            "https://e.com/1",
            "苹果 芯片 发布",
            "ithome",
            "tool",
            5.0,
            now - 600,
            True,
            today,
        ),
        HotItem(
            "Tool 2",
            "https://e.com/2",
            "华为 手机 新品",
            "ithome",
            "tool",
            5.0,
            now - 600,
            True,
            today,
        ),
        HotItem(
            "Tool 3",
            "https://f.com/1",
            "iPhone 评测",
            "sspai",
            "tool",
            5.0,
            now - 50000,
            True,
            yesterday,
        ),
        HotItem(
            "Tool 4",
            "https://f.com/2",
            "小米 笔记本",
            "sspai",
            "tool",
            5.0,
            now - 50000,
            True,
            today,
        ),
    ]
