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
    {
        "url": "https://www.infoq.cn/feed",
        "category": "ai",
        "source": "infoq",
        "tier": "vertical",
        "retention_hours": 48,
        "quality_weight": 3.5,
        "filter_profile": "standard",
    },
    {
        "url": "https://huggingface.co/blog/feed.xml",
        "category": "ai",
        "source": "huggingface_blog",
        "tier": "deep",
        "retention_hours": 72,
        "quality_weight": 4.0,
        "filter_profile": "lenient",
    },
    {
        "url": "https://rss.arxiv.org/rss/cs.AI",
        "category": "ai",
        "source": "arxiv_cs_ai",
        "tier": "deep",
        "retention_hours": 72,
        "quality_weight": 4.0,
        "filter_profile": "strict",
    },
    {
        "url": "https://rss.arxiv.org/rss/cs.CL",
        "category": "ai",
        "source": "arxiv_cs_cl",
        "tier": "deep",
        "retention_hours": 72,
        "quality_weight": 4.0,
        "filter_profile": "strict",
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
        "url": "https://www.oschina.net/news/rss",
        "category": "tool",
        "source": "oschina",
        "tier": "vertical",
        "retention_hours": 48,
        "quality_weight": 3.5,
        "filter_profile": "standard",
    },
    {
        "url": "https://www.v2ex.com/feed/tab/tech.xml",
        "category": "tool",
        "source": "v2ex_tech",
        "tier": "fast_news",
        "retention_hours": 24,
        "quality_weight": 2.0,
        "filter_profile": "strict",
        "max_selected_per_digest": 2,
    },
    {
        "url": "https://news.ycombinator.com/rss",
        "category": "tool",
        "source": "hacker_news",
        "tier": "vertical",
        "retention_hours": 48,
        "quality_weight": 3.5,
        "filter_profile": "standard",
    },
]

DEFAULT_DIGITAL_RSS_FEEDS = [
    {
        "url": "https://www.ithome.com/rss/",
        "category": "digital",
        "source": "ithome",
        "tier": "fast_news",
        "retention_hours": 24,
        "quality_weight": 2.0,
        "filter_profile": "strict",
        "dynamic_category": True,
    },
    {
        "url": "https://www.cnbeta.com.tw/backend.php",
        "category": "digital",
        "source": "cnbeta",
        "tier": "fast_news",
        "retention_hours": 24,
        "quality_weight": 2.0,
        "filter_profile": "strict",
        "max_selected_per_digest": 2,
        "dynamic_category": True,
    },
    {
        "url": "https://9to5mac.com/feed/",
        "category": "digital",
        "source": "9to5mac",
        "tier": "vertical",
        "retention_hours": 48,
        "quality_weight": 3.5,
        "filter_profile": "standard",
    },
    {
        "url": "https://techcrunch.com/feed/",
        "category": "digital",
        "source": "techcrunch",
        "tier": "vertical",
        "retention_hours": 48,
        "quality_weight": 3.5,
        "filter_profile": "standard",
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
    {
        "url": "https://www.gamesindustry.biz/feed",
        "category": "game",
        "source": "gamesindustry",
        "tier": "deep",
        "retention_hours": 72,
        "quality_weight": 4.0,
        "filter_profile": "lenient",
    },
    {
        "url": "https://www.nintendolife.com/feeds/latest",
        "category": "game",
        "source": "nintendo_life",
        "tier": "vertical",
        "retention_hours": 48,
        "quality_weight": 3.5,
        "filter_profile": "standard",
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


def _default_feeds_by_category() -> dict[str, list[dict]]:
    return {
        "ai": [dict(feed) for feed in DEFAULT_AI_RSS_FEEDS],
        "tool": [dict(feed) for feed in DEFAULT_TOOL_RSS_FEEDS],
        "game": [dict(feed) for feed in DEFAULT_GAME_RSS_FEEDS],
        "digital": [dict(feed) for feed in DEFAULT_DIGITAL_RSS_FEEDS],
    }


def load_effective_feed_configuration(path: Path | None = None) -> dict | None:
    """加载运行时有效配置，并把旧三分类 feeds.yaml 升级为四分类。

    本地同名来源覆盖默认策略；未声明的新默认来源仍保留，避免版本升级后
    已挂载的旧 feeds.yaml 阻断来源扩展。历史 ``tool/ithome`` 统一迁移到
    ``digital``，且从默认配置继承 ``dynamic_category``。
    """
    config = load_feed_configuration(path)
    if config is None or not isinstance(config.get("feeds"), dict):
        return config

    merged = _default_feeds_by_category()
    by_source = {
        feed["source"]: (category, index)
        for category, entries in merged.items()
        for index, feed in enumerate(entries)
    }
    for category in ("ai", "tool", "game", "digital"):
        entries = config["feeds"].get(category, [])
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("url"), str):
                continue
            source = entry.get("source", category)
            if not isinstance(source, str) or not source:
                source = category
            target_category = "digital" if source == "ithome" else category
            normalized = {**entry, "source": source, "category": target_category}
            existing = by_source.get(source)
            if existing is None:
                merged[target_category].append(normalized)
                by_source[source] = (target_category, len(merged[target_category]) - 1)
                continue

            existing_category, index = existing
            base = merged[existing_category][index]
            if existing_category != target_category:
                merged[existing_category].pop(index)
                for name, (known_category, known_index) in list(by_source.items()):
                    if known_category == existing_category and known_index > index:
                        by_source[name] = (known_category, known_index - 1)
                merged[target_category].append({**base, **normalized})
                by_source[source] = (target_category, len(merged[target_category]) - 1)
            else:
                merged[target_category][index] = {**base, **normalized}

    return {**config, "feeds": merged}


def _load_yaml_feeds() -> dict[str, list[dict]] | None:
    """读取升级后的运行时 feeds 配置。

    保留策略字段 (tier/retention_hours/quality_weight/filter_profile)，供后续任务使用。
    """
    config = load_effective_feed_configuration()
    if config is None or "feeds" not in config:
        return None
    raw = config["feeds"]
    result: dict[str, list[dict]] = {}
    for category in ("ai", "tool", "game", "digital"):
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
                    for key in (
                        "tier",
                        "retention_hours",
                        "quality_weight",
                        "filter_profile",
                        "max_selected_per_digest",
                        "dynamic_category",
                    ):
                        if key in e:
                            feed[key] = e[key]
                    result[category].append(feed)
        else:
            result[category] = []
    return result


def _get_defaults_for(category: str) -> list[dict]:
    if category == "ai":
        return list(DEFAULT_AI_RSS_FEEDS)
    if category == "tool":
        return list(DEFAULT_TOOL_RSS_FEEDS)
    if category == "game":
        return list(DEFAULT_GAME_RSS_FEEDS)
    if category == "digital":
        return list(DEFAULT_DIGITAL_RSS_FEEDS)
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


def load_digital_rss_feeds() -> list[dict]:
    defaults = _yaml_or_default("digital")
    return _load_feeds("DIGITAL_RSS_FEEDS", "DIGITAL_RSS_MODE", defaults, "digital")


def load_all_rss_feeds() -> list[dict]:
    return [
        *load_ai_rss_feeds(),
        *load_tool_rss_feeds(),
        *load_game_rss_feeds(),
        *load_digital_rss_feeds(),
    ]
