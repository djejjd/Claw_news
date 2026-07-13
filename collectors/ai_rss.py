from __future__ import annotations

import os
from pathlib import Path

FEEDS_YAML_PATH = Path(__file__).resolve().parent.parent / "feeds.yaml"

DEFAULT_AI_RSS_FEEDS = [
    {
        "url": "https://www.qbitai.com/feed",
        "category": "ai",
        "source": "qbitai",
        "tier": "vertical",
        "retention_hours": 48,
        "quality_weight": 3.5,
        "filter_profile": "standard",
    },
    {
        "url": "https://www.leiphone.com/feed",
        "category": "ai",
        "source": "leiphone",
        "tier": "vertical",
        "retention_hours": 48,
        "quality_weight": 3.5,
        "filter_profile": "standard",
    },
]

DEFAULT_TOOL_RSS_FEEDS = [
    {
        "url": "https://sspai.com/feed",
        "category": "tool",
        "source": "sspai",
        "tier": "vertical",
        "retention_hours": 48,
        "quality_weight": 3.5,
        "filter_profile": "standard",
    },
    {
        "url": "https://www.ithome.com/rss/",
        "category": "tool",
        "source": "ithome",
        "tier": "fast_news",
        "retention_hours": 24,
        "quality_weight": 2.0,
        "filter_profile": "strict",
    },
]

DEFAULT_GAME_RSS_FEEDS = [
    {
        "url": "https://www.yystv.cn/rss/feed",
        "category": "game",
        "source": "yystv",
        "tier": "vertical",
        "retention_hours": 48,
        "quality_weight": 3.5,
        "filter_profile": "standard",
    },
    {
        "url": "https://www.gcores.com/rss",
        "category": "game",
        "source": "gcores",
        "tier": "deep",
        "retention_hours": 72,
        "quality_weight": 4.0,
        "filter_profile": "lenient",
    },
]


def _parse_configured_feeds(raw: str) -> list[dict]:
    feeds: list[dict] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "|" not in chunk:
            raise ValueError("RSS_FEEDS entries must use source|url format")
        source, url = [part.strip() for part in chunk.split("|", 1)]
        if not source or not url:
            raise ValueError("RSS_FEEDS entries require both source and url")
        feeds.append({"source": source, "url": url, "category": "ai"})
    return feeds


def load_feed_configuration(path: Path | None = None) -> dict | None:
    """读取 feeds.yaml 完整顶层映射。

    返回包含 feeds 和可选的 relevance_rules 的完整 dict。
    文件不存在或解析失败返回 None。
    此为唯一读取 feeds.yaml 的公开入口。
    """
    target = path or FEEDS_YAML_PATH
    if not target.exists():
        return None
    try:
        import yaml

        with open(target, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            return None
        return data
    except Exception:
        return None


def _load_yaml_feeds() -> dict[str, list[dict]] | None:
    """Read feed categories from feeds.yaml；委托 load_feed_configuration()。

    保留策略字段 (tier/retention_hours/quality_weight/filter_profile)，供后续任务使用。
    """
    config = load_feed_configuration()
    if config is None or "feeds" not in config:
        return None
    raw = config["feeds"]
    result: dict[str, list[dict]] = {}
    for category in ("ai", "tool", "game"):
        entries = raw.get(category, [])
        if isinstance(entries, list):
            result[category] = []
            for e in entries:
                if isinstance(e, dict) and "url" in e:
                    feed = {
                        "url": e["url"],
                        "category": category,
                        "source": e.get("source", category),
                    }
                    # 保留来源策略字段
                    for key in ("tier", "retention_hours", "quality_weight", "filter_profile"):
                        if key in e:
                            feed[key] = e[key]
                    result[category].append(feed)
        else:
            result[category] = []
    return result
    # 解析异常由 load_feed_configuration 内部 catch


def _get_defaults_for(category: str) -> list[dict]:
    if category == "ai":
        return list(DEFAULT_AI_RSS_FEEDS)
    if category == "tool":
        return list(DEFAULT_TOOL_RSS_FEEDS)
    if category == "game":
        return list(DEFAULT_GAME_RSS_FEEDS)
    return []


def _load_feeds(env_name: str, mode_name: str, defaults: list[dict], category: str) -> list[dict]:
    raw = os.getenv(env_name, "").strip()
    mode = os.getenv(mode_name, "append").strip().lower() or "append"
    if mode not in {"append", "replace"}:
        raise ValueError(f"{mode_name} must be append or replace")

    configured = _parse_configured_feeds(raw) if raw else []
    configured = [{**feed, "category": category} for feed in configured]
    if mode == "replace":
        return configured
    return [*defaults, *configured]


def _yaml_or_default(category: str) -> list[dict]:
    """Return YAML feeds if file exists, otherwise hardcoded defaults."""
    yaml_feeds = _load_yaml_feeds()
    if yaml_feeds is not None and category in yaml_feeds and yaml_feeds[category]:
        return yaml_feeds[category]
    return _get_defaults_for(category)


def load_ai_rss_feeds() -> list[dict]:
    defaults = _yaml_or_default("ai")
    return _load_feeds("AI_RSS_FEEDS", "AI_RSS_MODE", defaults, "ai")


def load_tool_rss_feeds() -> list[dict]:
    defaults = _yaml_or_default("tool")
    return _load_feeds("TOOL_RSS_FEEDS", "TOOL_RSS_MODE", defaults, "tool")


def load_game_rss_feeds() -> list[dict]:
    defaults = _yaml_or_default("game")
    return _load_feeds("GAME_RSS_FEEDS", "GAME_RSS_MODE", defaults, "game")


def load_all_rss_feeds() -> list[dict]:
    return [
        *load_ai_rss_feeds(),
        *load_tool_rss_feeds(),
        *load_game_rss_feeds(),
    ]
