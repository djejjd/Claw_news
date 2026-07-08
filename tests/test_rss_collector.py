from unittest.mock import AsyncMock, patch

import pytest

from collectors.rss_sources import (
    FEED_CONFIGS,
    RssCollector,
    check_keyword_hit,
    extract_pub_date,
    strip_html,
)


def test_feed_configs_covers_three_categories():
    assert len(FEED_CONFIGS) >= 3
    for feed in FEED_CONFIGS:
        assert "url" in feed
        assert "category" in feed
        assert "source" in feed
    assert {feed["category"] for feed in FEED_CONFIGS} == {"ai", "tool", "game"}


def test_feed_configs_distinct_sources():
    sources = {feed["source"] for feed in FEED_CONFIGS}
    assert len(sources) == len(FEED_CONFIGS)  # all sources are unique


def test_strip_html():
    assert strip_html("<p>Hello <b>World</b></p>") == "Hello World"
    assert strip_html("plain text") == "plain text"
    assert strip_html("") == ""


def test_keyword_hit():
    kws = {"ai": ["AI", "GPT"]}
    assert check_keyword_hit("华为发布新AI大模型GPT", "", "ai", kws)
    assert not check_keyword_hit("今天天气真好", "", "ai", kws)


def test_extract_pub_date():
    ts = (2026, 5, 15, 10, 0, 0, 4, 136, 0)
    assert extract_pub_date(ts) == "2026-05-15"
    assert extract_pub_date(None) == ""


def test_parse_entry_full():
    collector = RssCollector(keywords={"ai": ["GPT", "大模型"]})
    entry = {
        "title": "GPT-5 发布",
        "link": "https://x.com/1",
        "summary": "<p>OpenAI <b>发布</b> GPT-5</p>",
        "published_parsed": (2026, 5, 15, 10, 0, 0, 4, 136, 0),
    }
    feed = {"url": "https://qbitai.com/feed", "category": "ai", "source": "qbitai"}
    item = collector._parse_entry(entry, feed)
    assert item.keyword_hit
    assert item.pub_date == "2026-05-15"
    assert "<" not in item.summary
    assert "GPT-5" in item.title
    assert item.source == "qbitai"
    assert item.category == "ai"


def test_parse_entry_missing():
    collector = RssCollector()
    item = collector._parse_entry(
        {"title": "X"}, {"url": "rss", "category": "game", "source": "yystv"}
    )
    assert item.url == ""
    assert not item.keyword_hit
    assert item.pub_date == ""
    assert item.source == "yystv"


def test_rss_collector_uses_injected_feeds():
    custom_feeds = [
        {"url": "https://custom.example.com/feed", "category": "ai", "source": "custom"},
    ]
    collector = RssCollector(
        feed_configs=custom_feeds,
        keywords={"ai": ["AI"]},
        fetch_count=3,
    )
    assert collector.feeds == custom_feeds
    assert collector._fetch_count == 3
    assert collector._keywords == {"ai": ["AI"]}


def test_rss_collector_defaults_to_feed_configs_when_none_provided():
    collector = RssCollector()
    assert collector.feeds == FEED_CONFIGS


def test_rss_collector_defaults_use_runtime_loader_feeds(monkeypatch):
    monkeypatch.setenv("TOOL_RSS_FEEDS", "custom_tool|https://custom.example.com/feed.xml")
    monkeypatch.setenv("TOOL_RSS_MODE", "replace")

    collector = RssCollector()
    tool_feeds = [feed for feed in collector.feeds if feed["category"] == "tool"]

    assert tool_feeds == [
        {
            "url": "https://custom.example.com/feed.xml",
            "category": "tool",
            "source": "custom_tool",
        }
    ]


@pytest.mark.asyncio
async def test_collect_fetches_feed_content_async_before_parsing():
    collector = RssCollector(
        feed_configs=[{"url": "https://example.com/feed", "category": "ai", "source": "example"}],
        fetch_count=2,
    )
    response = AsyncMock()
    response.text = "<rss></rss>"
    response.raise_for_status = lambda: None
    parsed = type("Parsed", (), {"entries": []})()

    with (
        patch("collectors.rss_sources.httpx.AsyncClient") as client_cls,
        patch("collectors.rss_sources.feedparser.parse", return_value=parsed) as parse_mock,
    ):
        client = AsyncMock()
        client.get.return_value = response
        client_cls.return_value.__aenter__.return_value = client

        await collector.collect()

    client.get.assert_awaited_once_with("https://example.com/feed", timeout=15.0)
    parse_mock.assert_called_once_with("<rss></rss>")


@pytest.mark.asyncio
async def test_collect_skips_feed_when_async_fetch_fails():
    collector = RssCollector(
        feed_configs=[{"url": "https://example.com/feed", "category": "ai", "source": "example"}],
    )

    with patch("collectors.rss_sources.httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client.get.side_effect = RuntimeError("timeout")
        client_cls.return_value.__aenter__.return_value = client

        items = await collector.collect()

    assert items == []


@pytest.mark.asyncio
async def test_collect_respects_runtime_fetch_count_limit():
    collector = RssCollector(
        feed_configs=[{"url": "https://example.com/feed", "category": "ai", "source": "example"}],
        fetch_count=2,
    )
    response = AsyncMock()
    response.text = "<rss></rss>"
    response.raise_for_status = lambda: None
    parsed = type(
        "Parsed",
        (),
        {
            "entries": [
                {"title": "1", "link": "https://example.com/1"},
                {"title": "2", "link": "https://example.com/2"},
                {"title": "3", "link": "https://example.com/3"},
            ]
        },
    )()

    with (
        patch("collectors.rss_sources.httpx.AsyncClient") as client_cls,
        patch("collectors.rss_sources.feedparser.parse", return_value=parsed),
    ):
        client = AsyncMock()
        client.get.return_value = response
        client_cls.return_value.__aenter__.return_value = client

        items = await collector.collect()

    assert len(items) == 2
