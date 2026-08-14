import pytest

from collectors.ai_rss import (
    DEFAULT_AI_RSS_FEEDS,
    _yaml_or_default,
    load_ai_rss_feeds,
    load_all_rss_feeds,
    load_digital_rss_feeds,
    load_effective_feed_configuration,
    load_feed_configuration,
    load_game_rss_feeds,
    load_tool_rss_feeds,
)

_PHASE2_SOURCE_CATEGORIES = {
    "oschina": "tool",
    "v2ex_tech": "tool",
    "hacker_news": "tool",
    "cnbeta": "digital",
    "9to5mac": "digital",
    "techcrunch": "digital",
    "gamesindustry": "game",
    "nintendo_life": "game",
    "infoq": "ai",
    "huggingface_blog": "ai",
    "arxiv_cs_ai": "ai",
    "arxiv_cs_cl": "ai",
}


def test_yaml_or_default_merges_local_feeds_with_phase2_defaults(tmp_path, monkeypatch):
    """本地来源保留，同时补齐版本新增的默认来源。"""
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
    assert next(feed for feed in feeds if feed["source"] == "custom_ai") == {
        "url": "https://custom.example/feed",
        "category": "ai",
        "source": "custom_ai",
    }
    assert any(feed["source"] == "infoq" for feed in feeds)


def test_yaml_or_default_preserves_source_selection_cap(tmp_path, monkeypatch):
    import yaml

    yaml_path = tmp_path / "feeds.yaml"
    yaml_path.write_text(
        yaml.safe_dump(
            {
                "feeds": {
                    "ai": [],
                    "tool": [
                        {
                            "url": "https://example.com/feed.xml",
                            "source": "custom_tool",
                            "max_selected_per_digest": 3,
                        }
                    ],
                    "game": [],
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("collectors.ai_rss.FEEDS_YAML_PATH", yaml_path)

    feeds = _yaml_or_default("tool")

    custom_tool = next(feed for feed in feeds if feed["source"] == "custom_tool")
    assert custom_tool["max_selected_per_digest"] == 3


def test_legacy_yaml_is_upgraded_without_duplicate_ithome_and_keeps_phase2_sources(
    tmp_path, monkeypatch
):
    """旧三分类配置不能阻断 Phase 2 来源或将 IT 之家保留在工具类。"""
    import yaml

    yaml_path = tmp_path / "feeds.yaml"
    yaml_path.write_text(
        yaml.safe_dump(
            {
                "feeds": {
                    "ai": [{"url": "https://custom.example/feed", "source": "custom_ai"}],
                    "tool": [
                        {
                            "url": "https://www.ithome.com/rss/",
                            "source": "ithome",
                            "tier": "fast_news",
                            "retention_hours": 24,
                            "quality_weight": 2.0,
                            "filter_profile": "strict",
                        }
                    ],
                    "game": [],
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("collectors.ai_rss.FEEDS_YAML_PATH", yaml_path)

    config = load_effective_feed_configuration()
    assert config is not None
    feeds = [feed for entries in config["feeds"].values() for feed in entries]
    ithome = [feed for feed in feeds if feed["source"] == "ithome"]

    assert len(ithome) == 1
    assert ithome[0]["category"] == "digital"
    assert ithome[0]["dynamic_category"] is True
    assert {"infoq", "cnbeta", "gamesindustry"}.issubset({feed["source"] for feed in feeds})


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


def test_digital_feeds_default_to_digital_category():
    feeds = load_digital_rss_feeds()

    assert len(feeds) >= 1
    assert all(feed["category"] == "digital" for feed in feeds)
    assert all("url" in feed and "source" in feed for feed in feeds)


def test_load_all_rss_feeds_contains_four_runtime_categories():
    feeds = load_all_rss_feeds()
    categories = {feed["category"] for feed in feeds}

    assert categories == {"ai", "tool", "game", "digital"}
    assert len(feeds) >= 4  # at least one per category


def test_phase2_approved_sources_have_stable_categories_and_fast_news_caps():
    """批准来源必须进入默认配置，快讯源保持硬上限策略。"""
    feeds_by_source = {feed["source"]: feed for feed in load_all_rss_feeds()}

    for source, category in _PHASE2_SOURCE_CATEGORIES.items():
        assert feeds_by_source[source]["category"] == category

    for source in ("v2ex_tech", "cnbeta"):
        feed = feeds_by_source[source]
        assert feed["tier"] == "fast_news"
        assert feed["retention_hours"] == 24
        assert feed["max_selected_per_digest"] == 2


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
