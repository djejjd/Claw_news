from datetime import date
from pathlib import Path
from typing import List

import httpx
import yaml
from bs4 import BeautifulSoup

from collectors.base import HotItem, normalize_rank_score, BROWSER_HEADERS

TAPTAP_HOT_URL = "https://www.taptap.cn/top/download"

_cfg = yaml.safe_load(open(Path(__file__).parent.parent / "config.yaml"))
TAPTAP_FETCH_COUNT = _cfg.get("collectors", {}).get("fetch_count", 10)


class TapTapCollector:
    """TapTap hot list crawler. Parses hot page HTML, extracts game names and links."""

    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client

    async def collect(self) -> List[HotItem]:
        client = self._client or httpx.AsyncClient(
            headers={**BROWSER_HEADERS, "Referer": "https://www.taptap.cn/"},
            follow_redirects=True,
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
        cells = soup.select(".game-list-cell")
        items = []
        for i, cell in enumerate(cells[:TAPTAP_FETCH_COUNT]):
            title_el = cell.select_one('[class*="title"]')
            title = title_el.get_text(strip=True) if title_el else ""
            app_link = cell.select_one('a[href*="/app/"]')
            href = app_link.get("href", "") if app_link else ""
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
                source_score=normalize_rank_score(i + 1, total=min(len(cells), TAPTAP_FETCH_COUNT)),
                pub_date=date.today().isoformat(),
            ))
        return items
