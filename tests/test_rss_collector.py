from collectors.rss_sources import RssCollector, FEED_CONFIGS


def test_feed_configs_have_required_fields():
    """Each feed config has url and category"""
    for feed in FEED_CONFIGS:
        assert "url" in feed
        assert "category" in feed
        assert feed["category"] in ("ai", "game", "device")


def test_parse_entry_to_hotitem():
    """Correctly construct HotItem from RSS entry dict"""
    collector = RssCollector()
    entry = {
        "title": "GPT-5 release shocks the industry",
        "link": "https://example.com/gpt5",
        "summary": "OpenAI officially released GPT-5 today...",
        "published_parsed": (2026, 5, 15, 10, 0, 0, 4, 136, 0),
    }
    feed = {"url": "https://example.com/rss", "category": "ai"}
    item = collector._parse_entry(entry, feed)
    assert item.title == "GPT-5 release shocks the industry"
    assert item.url == "https://example.com/gpt5"
    assert item.category == "ai"
    assert item.source == "rss"
    assert item.source_score == 5.0


def test_parse_entry_missing_fields():
    """Missing fields use defaults without crashing"""
    collector = RssCollector()
    entry = {"title": "No link item"}
    feed = {"url": "https://example.com/rss", "category": "game"}
    item = collector._parse_entry(entry, feed)
    assert item.title == "No link item"
    assert item.url == ""
    assert item.summary == ""
