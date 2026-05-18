from __future__ import annotations

import os

DEFAULT_AI_RSS_FEEDS = [
    {"url": "https://www.qbitai.com/feed", "category": "ai", "source": "qbitai"},
    {"url": "https://openai.com/news/rss.xml", "category": "ai", "source": "openai_blog"},
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
    raw = os.getenv("AI_RSS_FEEDS", "").strip()
    mode = os.getenv("AI_RSS_MODE", "append").strip().lower() or "append"
    if mode not in {"append", "replace"}:
        raise ValueError("AI_RSS_MODE must be append or replace")

    configured = _parse_configured_feeds(raw) if raw else []
    if mode == "replace":
        return configured
    return [*DEFAULT_AI_RSS_FEEDS, *configured]
