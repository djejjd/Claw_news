import time
from calendar import timegm
from typing import List

import feedparser

from collectors.base import HotItem, Category

# Each feed: url + category
FEED_CONFIGS: List[dict] = [
    {"url": "https://www.jiqizhixin.com/rss", "category": "ai"},
    {"url": "https://sspai.com/feed", "category": "device"},
    {"url": "https://www.yystv.cn/rss/feed", "category": "game"},
]


class RssCollector:
    """RSS multi-source collector. Iterates FEED_CONFIGS, takes last 10 entries from each, converts to HotItem."""

    def __init__(self, feed_configs: List[dict] | None = None):
        self.feeds = feed_configs or FEED_CONFIGS

    async def collect(self) -> List["HotItem"]:
        items = []
        for feed in self.feeds:
            parsed = feedparser.parse(feed["url"])
            entries = parsed.entries[:10]
            for entry in entries:
                items.append(self._parse_entry(entry, feed))
        return items

    def _parse_entry(self, entry: dict, feed: dict) -> "HotItem":
        title = entry.get("title", "")
        url = entry.get("link", "")
        summary = entry.get("summary", "")
        ts = _parse_timestamp(entry)

        return HotItem(
            title=title,
            url=url,
            summary=summary,
            source="rss",
            category=feed["category"],  # type: ignore[arg-type]
            source_score=5.0,
            timestamp=ts,
        )


def _parse_timestamp(entry: dict) -> float:
    """Extract timestamp from feedparser entry, fallback to current time"""
    published_parsed = entry.get("published_parsed")
    if published_parsed:
        return float(timegm(published_parsed))
    return time.time()
