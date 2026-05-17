"""RSS crawler — fetch and normalize news from RSS feeds."""

from __future__ import annotations

import asyncio
import logging

import feedparser

from collectors.rss_sources import extract_pub_date, strip_html

logger = logging.getLogger(__name__)


async def fetch_news(rss_urls: list[str], limit: int = 10) -> list[dict]:
    """Fetch news items from multiple RSS feeds.

    All feeds are collected fully before deduplication and truncation,
    so later feeds always participate regardless of earlier feed volume.
    Results are sorted by ``published_at`` descending (newest first).

    Args:
        rss_urls: List of RSS feed URLs.
        limit: Maximum number of results to return (default 10).

    Returns:
        List of dicts with keys: title, link, summary, published_at.
        Deduplicated by link (first occurrence kept).
    """
    seen: set[str] = set()
    raw: list[dict] = []

    for url in rss_urls:
        try:
            parsed = await asyncio.to_thread(feedparser.parse, url)
            for entry in parsed.entries:
                link = entry.get("link", "")
                if link and link in seen:
                    continue
                seen.add(link)
                raw.append(
                    {
                        "title": entry.get("title", ""),
                        "link": link,
                        "summary": strip_html(entry.get("summary", "")),
                        "published_at": extract_pub_date(
                            entry.get("published_parsed")
                        ),
                    }
                )
        except Exception:
            logger.warning("RSS feed %s failed", url, exc_info=True)

    raw.sort(key=lambda item: item["published_at"], reverse=True)
    return raw[:limit]
