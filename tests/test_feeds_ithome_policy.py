"""feeds.yaml 中 ithome 策略字段必须与内置降权一致，防止再次漂移。

注：feeds.yaml 被 gitignore，不入库；防漂移契约以受版本控制的
feeds.example.yaml 为准，故此处显式读取 example 文件。
"""

from pathlib import Path

from app.content.source_policy import build_source_policy_registry
from collectors.ai_rss import load_feed_configuration

EXAMPLE = Path(__file__).resolve().parent.parent / "feeds.example.yaml"


def _build_ithome_policy():
    feed_config = load_feed_configuration(EXAMPLE)
    assert feed_config is not None, "feeds.example.yaml 不存在或解析失败"
    feeds_raw = []
    for cat in ("ai", "tool", "game"):
        for f in feed_config.get("feeds", {}).get(cat, []):
            if isinstance(f, dict):
                feeds_raw.append({**f, "category": cat})
    registry = build_source_policy_registry(feeds_raw)
    return registry.get("ithome")


def test_ithome_has_reduced_quality_weight():
    policy = _build_ithome_policy()
    assert policy is not None, "feeds.yaml 中缺少 ithome 条目"
    assert policy.quality_weight == 2.0


def test_ithome_has_strict_filter():
    policy = _build_ithome_policy()
    assert policy is not None
    assert policy.filter_profile == "strict"


def test_ithome_retention_24h():
    policy = _build_ithome_policy()
    assert policy is not None
    assert policy.retention_hours == 24


def test_ithome_tier_fast_news():
    policy = _build_ithome_policy()
    assert policy is not None
    assert policy.tier == "fast_news"
