from collectors.rss_sources import (
    FEED_CONFIGS,
    RssCollector,
    check_keyword_hit,
    extract_pub_date,
    strip_html,
)


def test_feed_configs_has_4_feeds():
    assert len(FEED_CONFIGS) == 4
    for feed in FEED_CONFIGS:
        assert "url" in feed
        assert "category" in feed
        assert "source" in feed


def test_feed_configs_distinct_sources():
    sources = {feed["source"] for feed in FEED_CONFIGS}
    assert sources == {"qbitai", "sspai", "ithome", "yystv"}


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
