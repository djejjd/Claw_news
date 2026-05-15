from datetime import date
from typing import List

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

from collectors.base import HotItem, normalize_rank_score

TAPTAP_HOT_URL = "https://www.taptap.cn/top/download"


class TapTapCollector:
    """TapTap 下载榜爬虫，使用 curl_cffi 模拟 Chrome TLS 指纹过 WAF"""

    def __init__(self, fetch_count: int = 10, client=None):
        self._fetch_count = fetch_count
        self._client = client

    async def collect(self) -> List[HotItem]:
        if self._client is not None:
            resp = await self._client.get(TAPTAP_HOT_URL, timeout=30.0)
            resp.raise_for_status()
            html = resp.text
        else:
            session = curl_requests.AsyncSession(impersonate="chrome131")
            try:
                resp = await session.get(TAPTAP_HOT_URL, timeout=30.0)
                resp.raise_for_status()
                html = resp.text
            finally:
                await session.close()
        return self._parse_html(html)

    def _parse_html(self, html: str) -> List[HotItem]:
        soup = BeautifulSoup(html, "html.parser")
        cells = soup.select(".game-list-cell")
        items = []
        for i, cell in enumerate(cells[: self._fetch_count]):
            title_el = cell.select_one('[class*="title"]')
            title = title_el.get_text(strip=True) if title_el else ""
            app_link = cell.select_one('a[href*="/app/"]')
            href = app_link.get("href", "") if app_link else ""
            if href and not href.startswith("http"):
                href = f"https://www.taptap.cn{href}"

            if not title or not href:
                continue

            items.append(
                HotItem(
                    title=title,
                    url=href,
                    summary="",
                    source="taptap",
                    category="game",
                    source_score=normalize_rank_score(
                        i + 1, total=min(len(cells), self._fetch_count)
                    ),
                    pub_date=date.today().isoformat(),
                )
            )
        return items
