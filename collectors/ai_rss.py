from __future__ import annotations

import os
from pathlib import Path

FEEDS_YAML_PATH = Path(__file__).resolve().parent.parent / "feeds.yaml"

DEFAULT_AI_RSS_FEEDS = [
    {"url": "https://www.qbitai.com/feed", "category": "ai", "source": "qbitai"},
    {"url": "https://www.leiphone.com/feed", "category": "ai", "source": "leiphone"},
]

DEFAULT_TOOL_RSS_FEEDS = [
    {"url": "https://sspai.com/feed", "category": "tool", "source": "sspai"},
    {"url": "https://www.ithome.com/rss/", "category": "tool", "source": "ithome"},
]

DEFAULT_GAME_RSS_FEEDS = [
    {"url": "https://www.yystv.cn/rss/feed", "category": "game", "source": "yystv"},
    {"url": "https://www.gcores.com/rss", "category": "game", "source": "gcores"},
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


def _load_yaml_feeds() -> dict[str, list[dict]] | None:
    """Read feeds from feeds.yaml if it exists, return None if missing or unparseable."""
    if not FEEDS_YAML_PATH.exists():
        return None
    try:
        import yaml

        with open(FEEDS_YAML_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict) or "feeds" not in data:
            return None
        raw = data["feeds"]
        result: dict[str, list[dict]] = {}
        for category in ("ai", "tool", "game"):
            entries = raw.get(category, [])
            if isinstance(entries, list):
                result[category] = [
                    {
                        "url": e["url"],
                        "category": category,
                        "source": e.get("source", category),
                    }
                    for e in entries
                    if isinstance(e, dict) and "url" in e
                ]
            else:
                result[category] = []
        return result
    except Exception:
        return None


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
