import re
import time
from calendar import timegm
from typing import List

import feedparser

from collectors.base import HotItem, BROWSER_HEADERS

# 设置 feedparser 的 User-Agent，防止被 RSS 源拦截
feedparser.USER_AGENT = BROWSER_HEADERS["User-Agent"]

FEED_CONFIGS: List[dict] = [
    {"url": "https://www.qbitai.com/feed", "category": "ai", "source": "qbitai"},
    {"url": "https://sspai.com/feed", "category": "device", "source": "sspai"},
    {"url": "https://www.ithome.com/rss/", "category": "device", "source": "ithome"},
    {"url": "https://www.yystv.cn/rss/feed", "category": "game", "source": "yystv"},
]


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def check_keyword_hit(title: str, summary: str, category: str, keywords: dict) -> bool:
    kws = keywords.get(category, [])
    text = (title + " " + summary).lower()
    return any(kw.lower() in text for kw in kws)


def extract_pub_date(published_parsed) -> str:
    if published_parsed and len(published_parsed) >= 3:
        return f"{published_parsed[0]:04d}-{published_parsed[1]:02d}-{published_parsed[2]:02d}"
    return ""


class RssCollector:
    def __init__(self, feed_configs: List[dict] | None = None, keywords: dict | None = None, fetch_count: int = 10):
        self.feeds = feed_configs or FEED_CONFIGS
        self._keywords = keywords or {}
        self._fetch_count = fetch_count

    async def collect(self) -> List["HotItem"]:
        import logging
        logger = logging.getLogger(__name__)
        items = []
        for feed in self.feeds:
            try:
                parsed = feedparser.parse(feed["url"])
                for entry in parsed.entries[:self._fetch_count]:
                    items.append(self._parse_entry(entry, feed))
            except Exception as e:
                logger.warning("RSS feed %s failed: %s", feed["url"], e)
        return items

    def _parse_entry(self, entry: dict, feed: dict) -> "HotItem":
        title = entry.get("title", "")
        url = entry.get("link", "")
        summary = strip_html(entry.get("summary", ""))
        ts = _parse_timestamp(entry)
        pub_date = extract_pub_date(entry.get("published_parsed"))
        cat = feed["category"]
        source_name = feed.get("source", cat)
        kw_hit = check_keyword_hit(title, summary, cat, self._keywords)

        return HotItem(
            title=title, url=url, summary=summary,
            source=source_name, category=cat,  # type: ignore[arg-type]
            source_score=5.0, timestamp=ts,
            keyword_hit=kw_hit, pub_date=pub_date,
        )


def _parse_timestamp(entry: dict) -> float:
    pp = entry.get("published_parsed")
    return float(timegm(pp)) if pp else time.time()
