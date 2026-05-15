from typing import List

import httpx
from bs4 import BeautifulSoup

from collectors.base import HotItem, normalize_rank_score

ITHOME_RANK_URL = "https://m.ithome.com/rank/"


class ItHomeCollector:
    """ITHome hot list crawler. Parses mobile rank page HTML."""

    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client

    async def collect(self) -> List[HotItem]:
        client = self._client or httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15"}
        )
        try:
            resp = await client.get(ITHOME_RANK_URL, timeout=30.0)
            resp.raise_for_status()
            items = self._parse_html(resp.text)
        finally:
            if self._client is None:
                await client.aclose()
        return items

    def _parse_html(self, html: str) -> List[HotItem]:
        soup = BeautifulSoup(html, "html.parser")
        rank_items = soup.select(".rank-item")
        items = []
        for i, item in enumerate(rank_items[:10]):
            link = item.select_one("a.title")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if not title or not href:
                continue

            items.append(HotItem(
                title=title,
                url=href,
                summary="",
                source="ithome",
                category="device",
                source_score=normalize_rank_score(i + 1, total=min(len(rank_items), 10)),
            ))
        return items
