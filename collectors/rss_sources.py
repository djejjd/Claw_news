import asyncio
import re
import time
from calendar import timegm
from typing import List

import feedparser
import httpx

from collectors.ai_rss import load_all_rss_feeds
from collectors.base import BROWSER_HEADERS, HotItem

# 设置 feedparser 的 User-Agent，防止被 RSS 源拦截
feedparser.USER_AGENT = BROWSER_HEADERS["User-Agent"]
HTTP_TIMEOUT = 15.0

# FEED_CONFIGS 从 feeds.yaml（或代码默认值）动态加载
FEED_CONFIGS: List[dict] = load_all_rss_feeds()


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def extract_pub_date(published_parsed) -> str:
    """返回 yyyy-mm-dd（向后兼容）。"""
    if published_parsed and len(published_parsed) >= 3:
        return f"{published_parsed[0]:04d}-{published_parsed[1]:02d}-{published_parsed[2]:02d}"
    return ""


def format_published_iso(published_parsed) -> str:
    """将 feedparser 的 published_parsed 转为完整 ISO 时间。

    返回 yyyy-mm-ddTHH:MM:SS 或空字符串。
    """
    if not published_parsed or len(published_parsed) < 6:
        return ""
    try:
        return (
            f"{published_parsed[0]:04d}-{published_parsed[1]:02d}-{published_parsed[2]:02d}"
            f"T{published_parsed[3]:02d}:{published_parsed[4]:02d}:{published_parsed[5]:02d}"
        )
    except (TypeError, IndexError):
        return ""


class RssCollector:
    def __init__(
        self,
        feed_configs: List[dict] | None = None,
        fetch_count: int = 10,
        client: httpx.AsyncClient | None = None,
    ):
        self.feeds = feed_configs if feed_configs is not None else load_all_rss_feeds()
        self._fetch_count = fetch_count
        self._client = client
        # 本轮失败的 feed，供调度层读取部分失败信息
        self.failed_feeds: list[str] = []

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
                    self.failed_feeds.append(f"{feed.get('source', feed['url'])}: {e}")
                    logger.warning("RSS feed %s failed: %s", feed["url"], e)
            return items

        async with httpx.AsyncClient(headers=BROWSER_HEADERS, follow_redirects=True) as client:
            for feed in self.feeds:
                try:
                    parsed = await self._fetch_and_parse(feed["url"], client)
                    for entry in parsed.entries[: self._fetch_count]:
                        items.append(self._parse_entry(entry, feed))
                except Exception as e:
                    self.failed_feeds.append(f"{feed.get('source', feed['url'])}: {e}")
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
        pp = entry.get("published_parsed")
        # 优先完整 ISO 时间，回退到 yyyy-mm-dd
        pub_date = format_published_iso(pp) or extract_pub_date(pp)
        cat = feed["category"]
        source_name = feed.get("source", cat)

        return HotItem(
            title=title,
            url=url,
            summary=summary,
            source=source_name,
            category=cat,  # type: ignore[arg-type]
            source_score=5.0,
            timestamp=ts,
            keyword_hit=False,
            pub_date=pub_date,
        )


def _parse_timestamp(entry: dict) -> float:
    pp = entry.get("published_parsed")
    return float(timegm(pp)) if pp else time.time()
