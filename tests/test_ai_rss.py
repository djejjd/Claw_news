import pytest

from collectors.ai_rss import (
    DEFAULT_AI_RSS_FEEDS,
    _yaml_or_default,
    load_ai_rss_feeds,
    load_all_rss_feeds,
    load_feed_configuration,
    load_game_rss_feeds,
    load_tool_rss_feeds,
)


def test_yaml_or_default_respects_yaml_file(tmp_path, monkeypatch):
    """When feeds.yaml exists, _yaml_or_default reads from it."""
    import yaml

    yaml_path = tmp_path / "feeds.yaml"
    yaml_path.write_text(
        yaml.dump(
            {
                "feeds": {
                    "ai": [{"url": "https://custom.example/feed", "source": "custom_ai"}],
                    "tool": [{"url": "https://t.example/feed", "source": "custom_tool"}],
                    "game": [{"url": "https://g.example/feed", "source": "custom_game"}],
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("collectors.ai_rss.FEEDS_YAML_PATH", yaml_path)

    feeds = _yaml_or_default("ai")
    assert feeds == [
        {
            "url": "https://custom.example/feed",
            "category": "ai",
            "source": "custom_ai",
        }
    ]


def test_load_feed_configuration_preserves_top_level_relevance_rules(tmp_path):
    """完整配置读取必须保留 Task 4 所需的顶层规则。"""
    import yaml

    yaml_path = tmp_path / "feeds.yaml"
    yaml_path.write_text(
        yaml.dump(
            {
                "feeds": {"ai": [], "tool": [], "game": []},
                "relevance_rules": {"ai": {"positive": ["自定义"], "negative": []}},
            }
        ),
        encoding="utf-8",
    )

    config = load_feed_configuration(yaml_path)

    assert config is not None
    assert config["relevance_rules"]["ai"]["positive"] == ["自定义"]


def test_yaml_or_default_falls_back_when_file_missing(monkeypatch, tmp_path):
    """When feeds.yaml is absent, fall back to hardcoded defaults."""
    monkeypatch.setattr("collectors.ai_rss.FEEDS_YAML_PATH", tmp_path / "nonexistent.yaml")
    feeds = _yaml_or_default("ai")
    assert feeds == DEFAULT_AI_RSS_FEEDS


def test_defaults_return_ai_feeds(monkeypatch):
    monkeypatch.delenv("AI_RSS_FEEDS", raising=False)
    monkeypatch.delenv("AI_RSS_MODE", raising=False)

    feeds = load_ai_rss_feeds()

    assert len(feeds) >= 1
    assert all(feed["category"] == "ai" for feed in feeds)
    assert all("url" in feed and "source" in feed for feed in feeds)


def test_tool_feeds_default_to_tool_category():
    feeds = load_tool_rss_feeds()

    assert len(feeds) >= 1
    assert all(feed["category"] == "tool" for feed in feeds)
    assert all("url" in feed and "source" in feed for feed in feeds)


def test_game_feeds_default_to_game_category():
    feeds = load_game_rss_feeds()

    assert len(feeds) >= 1
    assert all(feed["category"] == "game" for feed in feeds)
    assert all("url" in feed and "source" in feed for feed in feeds)


def test_load_all_rss_feeds_contains_ai_tool_game():
    feeds = load_all_rss_feeds()
    categories = {feed["category"] for feed in feeds}

    assert categories == {"ai", "tool", "game"}
    assert len(feeds) >= 3  # at least one per category


def test_append_mode_keeps_defaults_and_adds_configured_feed(monkeypatch):
    monkeypatch.setenv("AI_RSS_MODE", "append")
    monkeypatch.setenv("AI_RSS_FEEDS", "custom_ai|https://example.com/feed.xml")

    feeds = load_ai_rss_feeds()

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
