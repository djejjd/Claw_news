import asyncio
import re
import time
from calendar import timegm
from typing import List

import feedparser
import httpx

from collectors.base import BROWSER_HEADERS, HotItem

# 设置 feedparser 的 User-Agent，防止被 RSS 源拦截
feedparser.USER_AGENT = BROWSER_HEADERS["User-Agent"]
HTTP_TIMEOUT = 15.0

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
    def __init__(
        self,
        feed_configs: List[dict] | None = None,
        keywords: dict | None = None,
        fetch_count: int = 10,
        client: httpx.AsyncClient | None = None,
    ):
        self.feeds = feed_configs or FEED_CONFIGS
        self._keywords = keywords or {}
        self._fetch_count = fetch_count
        self._client = client

    async def collect(self) -> List["HotItem"]:
        import logging

        logger = logging.getLogger(__name__)
        items = []
        if self._client is not None:
            for feed in self.feeds:
                try:
                    parsed = await self._fetch_and_parse(feed["url"], self._client)
                    for entry in parsed.entries[: self._fetch_count]:
                        items.append(self._parse_entry(entry, feed))
                except Exception as e:
                    logger.warning("RSS feed %s failed: %s", feed["url"], e)
            return items

        async with httpx.AsyncClient(headers=BROWSER_HEADERS, follow_redirects=True) as client:
            for feed in self.feeds:
                try:
                    parsed = await self._fetch_and_parse(feed["url"], client)
                    for entry in parsed.entries[: self._fetch_count]:
                        items.append(self._parse_entry(entry, feed))
                except Exception as e:
                    logger.warning("RSS feed %s failed: %s", feed["url"], e)
        return items

    async def _fetch_and_parse(self, url: str, client: httpx.AsyncClient):
        response = await client.get(url, timeout=HTTP_TIMEOUT)
        response.raise_for_status()
        return await asyncio.to_thread(feedparser.parse, response.text)

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
            title=title,
            url=url,
            summary=summary,
            source=source_name,
            category=cat,  # type: ignore[arg-type]
            source_score=5.0,
            timestamp=ts,
            keyword_hit=kw_hit,
            pub_date=pub_date,
        )


def _parse_timestamp(entry: dict) -> float:
    pp = entry.get("published_parsed")
    return float(timegm(pp)) if pp else time.time()
