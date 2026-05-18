import pytest

from collectors.ai_rss import DEFAULT_AI_RSS_FEEDS, load_ai_rss_feeds


def test_defaults_return_ai_feeds(monkeypatch):
    monkeypatch.delenv("AI_RSS_FEEDS", raising=False)
    monkeypatch.delenv("AI_RSS_MODE", raising=False)

    feeds = load_ai_rss_feeds()

    assert feeds == DEFAULT_AI_RSS_FEEDS
    assert all(feed["category"] == "ai" for feed in feeds)
    assert len(feeds) >= 2


def test_append_mode_keeps_defaults_and_adds_configured_feed(monkeypatch):
    monkeypatch.setenv("AI_RSS_MODE", "append")
    monkeypatch.setenv("AI_RSS_FEEDS", "custom_ai|https://example.com/feed.xml")

    feeds = load_ai_rss_feeds()

    assert feeds[: len(DEFAULT_AI_RSS_FEEDS)] == DEFAULT_AI_RSS_FEEDS
    assert feeds[-1] == {
        "source": "custom_ai",
        "url": "https://example.com/feed.xml",
        "category": "ai",
    }


def test_replace_mode_uses_only_configured_feeds(monkeypatch):
    monkeypatch.setenv("AI_RSS_MODE", "replace")
    monkeypatch.setenv(
        "AI_RSS_FEEDS",
        "custom_ai|https://example.com/feed.xml,other_ai|https://other.example/feed",
    )

    feeds = load_ai_rss_feeds()

    assert feeds == [
        {"source": "custom_ai", "url": "https://example.com/feed.xml", "category": "ai"},
        {"source": "other_ai", "url": "https://other.example/feed", "category": "ai"},
    ]


@pytest.mark.parametrize(
    "raw",
    [
        "missing_separator",
        "|https://example.com/feed.xml",
        "custom_ai|",
    ],
)
def test_malformed_config_is_rejected(monkeypatch, raw):
    monkeypatch.setenv("AI_RSS_MODE", "replace")
    monkeypatch.setenv("AI_RSS_FEEDS", raw)

    with pytest.raises(ValueError):
        load_ai_rss_feeds()
