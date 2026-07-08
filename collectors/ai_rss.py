from __future__ import annotations

import os

DEFAULT_AI_RSS_FEEDS = [
    {"url": "https://www.qbitai.com/feed", "category": "ai", "source": "qbitai"},
    {"url": "https://www.jiqizhixin.com/rss", "category": "ai", "source": "jiqizhixin"},
]

DEFAULT_TOOL_RSS_FEEDS = [
    {"url": "https://sspai.com/feed", "category": "tool", "source": "sspai"},
    {"url": "https://www.ithome.com/rss/", "category": "tool", "source": "ithome"},
]

DEFAULT_GAME_RSS_FEEDS = [
    {"url": "https://www.yystv.cn/rss/feed", "category": "game", "source": "yystv"},
    {"url": "https://www.gamelook.com.cn/feed", "category": "game", "source": "gamelook"},
]


def _parse_configured_feeds(raw: str) -> list[dict]:
    feeds: list[dict] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "|" not in chunk:
            raise ValueError("AI_RSS_FEEDS entries must use source|url format")
        source, url = [part.strip() for part in chunk.split("|", 1)]
        if not source or not url:
            raise ValueError("AI_RSS_FEEDS entries require both source and url")
        feeds.append({"source": source, "url": url, "category": "ai"})
    return feeds


def load_ai_rss_feeds() -> list[dict]:
    return _load_feeds("AI_RSS_FEEDS", "AI_RSS_MODE", DEFAULT_AI_RSS_FEEDS, "ai")


def load_tool_rss_feeds() -> list[dict]:
    return _load_feeds("TOOL_RSS_FEEDS", "TOOL_RSS_MODE", DEFAULT_TOOL_RSS_FEEDS, "tool")


def load_game_rss_feeds() -> list[dict]:
    return _load_feeds("GAME_RSS_FEEDS", "GAME_RSS_MODE", DEFAULT_GAME_RSS_FEEDS, "game")


def load_all_rss_feeds() -> list[dict]:
    return [
        *load_ai_rss_feeds(),
        *load_tool_rss_feeds(),
        *load_game_rss_feeds(),
    ]


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
