"""Task 2: source_policy 失败测试 — 模块/接口不存在时预期失败。"""

import pytest


def test_module_importable():
    """验证模块可导入 — 实现前应失败 (ModuleNotFoundError)。"""
    from app.content.source_policy import (  # noqa: F401
        DEFAULT_SOURCE_POLICY,
        SourcePolicy,
        build_source_policy_registry,
        resolve_source_policy,
    )


def test_default_policy_values():
    """默认策略的值符合设计第 6.2 节。"""
    from app.content.source_policy import SourcePolicy

    p = SourcePolicy(source="test")
    assert p.tier == "vertical"
    assert p.retention_hours == 48
    assert p.quality_weight == 3.0
    assert p.filter_profile == "standard"


def test_missing_policy_uses_conservative_default():
    """缺少显式策略的源使用保守默认值。"""
    from app.content.source_policy import SourcePolicy, build_source_policy_registry

    registry = build_source_policy_registry([{
        "source": "new_source", "url": "https://x.test/feed", "category": "ai",
    }])
    assert registry["new_source"] == SourcePolicy(
        source="new_source", tier="vertical", retention_hours=48,
        quality_weight=3.0, filter_profile="standard",
    )


@pytest.mark.parametrize("field,value", [
    ("tier", "unknown"),
    ("retention_hours", 0),
    ("quality_weight", -1),
    ("filter_profile", "open"),
])
def test_explicit_invalid_policy_raises(field, value):
    """非法显式策略必须指出 source 和字段并失败。"""
    from app.content.source_policy import build_source_policy_registry

    feed = {"source": "bad", "url": "https://x.test", "category": "ai", field: value}
    with pytest.raises(ValueError, match="bad"):
        build_source_policy_registry([feed])


def _make_feed(source, url, cat, tier, rh, qw, fp):
    return {
        "source": source, "url": url, "category": cat,
        "tier": tier, "retention_hours": rh,
        "quality_weight": qw, "filter_profile": fp,
    }


def test_all_default_sources_have_explicit_policy():
    """所有 feeds.example.yaml 中的默认源都有明确策略。"""
    from app.content.source_policy import build_source_policy_registry

    f = _make_feed
    feeds = [
        f("ithome", "https://www.ithome.com/rss/", "tool", "fast_news", 24, 2.0, "strict"),
        f("taptap", "https://www.taptap.cn/top/download",
          "game", "fast_news", 24, 2.5, "strict"),
        f("eurogamer", "https://www.eurogamer.net/?format=rss",
          "game", "fast_news", 24, 3.0, "strict"),
        f("qbitai", "https://www.qbitai.com/feed", "ai", "vertical", 48, 3.5, "standard"),
        f("leiphone", "https://www.leiphone.com/feed", "ai", "vertical", 48, 3.5, "standard"),
        f("jiqizhixin", "https://decemberpei.cyou/rssbox/wechat-jiqizhixin.xml",
          "ai", "vertical", 48, 3.5, "standard"),
        f("sspai", "https://sspai.com/feed", "tool", "vertical", 48, 3.5, "standard"),
        f("appinn", "https://www.appinn.com/feed", "tool", "vertical", 48, 3.5, "standard"),
        f("yystv", "https://www.yystv.cn/rss/feed", "game", "vertical", 48, 3.5, "standard"),
        f("indienova", "https://indienova.com/feed/", "game", "vertical", 48, 3.5, "standard"),
        f("gcores", "https://www.gcores.com/rss", "game", "deep", 72, 4.0, "lenient"),
        f("chuapp", "https://www.chuapp.com/feed", "game", "deep", 72, 4.0, "lenient"),
        f("meituan_tech", "https://tech.meituan.com/feed/", "ai", "deep", 72, 4.0, "lenient"),
        f("cloudflare_cn", "https://blog.cloudflare.com/zh-cn/rss",
          "tool", "deep", 72, 4.0, "lenient"),
        f("huggingface", "https://huggingface.co/blog/feed.xml",
          "ai", "deep", 72, 4.0, "lenient"),
    ]
    registry = build_source_policy_registry(feeds)
    assert len(registry) == 15
    assert registry["ithome"].tier == "fast_news"
    assert registry["gcores"].tier == "deep"
    assert registry["qbitai"].quality_weight == 3.5


def test_resolve_source_policy():
    """resolve_source_policy 从 registry 查找策略。"""
    from app.content.source_policy import (
        SourcePolicy,
        build_source_policy_registry,
        resolve_source_policy,
    )

    registry = build_source_policy_registry([{
        "source": "qbitai", "url": "https://www.qbitai.com/feed", "category": "ai",
        "tier": "vertical", "retention_hours": 48, "quality_weight": 3.5,
        "filter_profile": "standard",
    }])
    p = resolve_source_policy("qbitai", registry)
    assert isinstance(p, SourcePolicy)
    assert p.source == "qbitai"


def test_duplicate_source_last_wins():
    """两个 feed 使用同一个 source 名时，后者覆盖前者。"""
    from app.content.source_policy import build_source_policy_registry

    feeds = [
        {"source": "dup", "url": "https://first.test", "category": "ai",
         "tier": "fast_news", "retention_hours": 24,
         "quality_weight": 2.0, "filter_profile": "strict"},
        {"source": "dup", "url": "https://second.test", "category": "ai",
         "tier": "deep", "retention_hours": 72,
         "quality_weight": 4.0, "filter_profile": "lenient"},
    ]
    registry = build_source_policy_registry(feeds)
    assert len(registry) == 1
    assert registry["dup"].tier == "deep"
    assert registry["dup"].quality_weight == 4.0


def test_resolve_unknown_source_uses_default():
    """未知源返回保守默认策略。"""
    from app.content.source_policy import SourcePolicy, resolve_source_policy

    p = resolve_source_policy("never_seen_source", {})
    assert p == SourcePolicy(source="never_seen_source")
