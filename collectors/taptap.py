from typing import List

import httpx
from bs4 import BeautifulSoup

from collectors.base import HotItem, normalize_rank_score

TAPTAP_HOT_URL = "https://www.taptap.cn/top/hot"


class TapTapCollector:
    """TapTap hot list crawler. Parses hot page HTML, extracts game names and links."""

    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client

    async def collect(self) -> List[HotItem]:
        client = self._client or httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        )
        try:
            resp = await client.get(TAPTAP_HOT_URL, timeout=30.0)
            resp.raise_for_status()
            items = self._parse_html(resp.text)
        finally:
            if self._client is None:
                await client.aclose()
        return items

    def _parse_html(self, html: str) -> List[HotItem]:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("a.game-card")
        items = []
        for i, card in enumerate(cards[:10]):
            title_el = card.select_one("h3")
            title = title_el.get_text(strip=True) if title_el else ""
            href = card.get("href", "")
            if href and not href.startswith("http"):
                href = f"https://www.taptap.cn{href}"

            if not title or not href:
                continue

            items.append(HotItem(
                title=title,
                url=href,
                summary="",
                source="taptap",
                category="game",
                source_score=normalize_rank_score(i + 1, total=min(len(cards), 10)),
            ))
        return items
