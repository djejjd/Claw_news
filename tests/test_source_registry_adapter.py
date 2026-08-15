from app.publication.source_registry import SourceRegistryAdapter


def test_adapter_separates_stable_source_default_category_and_rss_feed():
    specs = SourceRegistryAdapter.from_feed_configuration(
        {
            "feeds": {
                "digital": [
                    {
                        "source": "ithome",
                        "url": "https://www.ithome.com/rss/",
                        "dynamic_category": True,
                    }
                ]
            },
            "source_policies": {
                "taptap": {"source": "taptap", "tier": "fast_news"},
            },
        }
    )

    by_name = {spec["name"]: spec for spec in specs}
    assert by_name["ithome"]["default_category"] == "digital"
    assert by_name["ithome"]["feeds"] == [
        {
            "url": "https://www.ithome.com/rss/",
            "collector_type": "rss",
            "strategy": {"dynamic_category": True},
        }
    ]
    assert by_name["taptap"]["feeds"] == [
        {
            "url": "https://www.taptap.cn/top/download",
            "collector_type": "crawler",
            "strategy": {"tier": "fast_news"},
        }
    ]
    assert by_name["github"]["default_category"] == "tool"


def test_adapter_uses_runtime_rss_defaults_when_no_feed_configuration(monkeypatch):
    monkeypatch.setattr(
        "collectors.ai_rss.load_all_rss_feeds",
        lambda: [
            {
                "source": "default_ai",
                "url": "https://example.test/default.xml",
                "category": "ai",
            }
        ],
    )

    specs = SourceRegistryAdapter.from_feed_configuration(None)

    default_ai = next(spec for spec in specs if spec["name"] == "default_ai")
    assert default_ai["default_category"] == "ai"
    assert default_ai["feeds"][0]["url"] == "https://example.test/default.xml"
