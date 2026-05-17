"""RSS crawler — fetch and normalize news from RSS feeds."""

from __future__ import annotations

import asyncio
import logging

import feedparser

from collectors.rss_sources import extract_pub_date, strip_html

logger = logging.getLogger(__name__)


async def fetch_news(rss_urls: list[str], limit: int = 10) -> list[dict]:
    """Fetch news items from multiple RSS feeds.

    Args:
        rss_urls: List of RSS feed URLs.
        limit: Maximum number of results to return (default 10).

    Returns:
        List of dicts with keys: title, link, summary, published_at.
        Deduplicated by link (first occurrence kept).
    """
    seen: set[str] = set()
    results: list[dict] = []

    for url in rss_urls:
        try:
            parsed = await asyncio.to_thread(feedparser.parse, url)
            for entry in parsed.entries:
                if len(results) >= limit:
                    break
                link = entry.get("link", "")
                if link and link in seen:
                    continue
                seen.add(link)
                results.append(
                    {
                        "title": entry.get("title", ""),
                        "link": link,
                        "summary": strip_html(entry.get("summary", "")),
                        "published_at": extract_pub_date(entry.get("published_parsed")),
                    }
                )
        except Exception:
            logger.warning("RSS feed %s failed", url, exc_info=True)

        if len(results) >= limit:
            break

    return results[:limit]
