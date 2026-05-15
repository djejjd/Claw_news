from datetime import date
from pathlib import Path
from typing import List

import httpx
import yaml

from collectors.base import HotItem

HF_API_URL = "https://huggingface.co/api/daily_papers"

_cfg = yaml.safe_load(open(Path(__file__).parent.parent / "config.yaml"))
HF_FETCH_COUNT = _cfg.get("collectors", {}).get("fetch_count", 10)


class HfDailyPapersCollector:
    """HuggingFace Daily Papers API collector. Sorted by community votes, takes top N."""

    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client

    async def collect(self) -> List[HotItem]:
        client = self._client or httpx.AsyncClient()
        try:
            resp = await client.get(HF_API_URL, timeout=30.0)
            resp.raise_for_status()
            papers = resp.json()
        finally:
            if self._client is None:
                await client.aclose()

        max_votes = max((p.get("upvotes", 0) for p in papers), default=1)
        papers.sort(key=lambda p: p.get("upvotes", 0), reverse=True)
        items = [self._parse_paper(p, max_votes) for p in papers[:HF_FETCH_COUNT]]
        return items

    def _parse_paper(self, paper: dict, max_votes: int | None = None) -> HotItem:
        title = paper.get("title", "")
        paper_id = (paper.get("paper") or {}).get("id", "")
        upvotes = paper.get("upvotes", 0)
        summary = paper.get("summary", "")

        if max_votes is None:
            max_votes = max(upvotes, 1)

        return HotItem(
            title=title,
            url=f"https://huggingface.co/papers/{paper_id}",
            summary=summary,
            source="huggingface",
            category="ai",
            source_score=self._upvotes_to_score(upvotes, max_votes),
            pub_date=date.today().isoformat(),
        )

    def _upvotes_to_score(self, upvotes: int, max_votes: int) -> float:
        """Normalize upvotes to 0-10. max_votes maps to 10, 0 maps to 0."""
        if max_votes <= 0:
            return 0.0
        ratio = upvotes / max_votes
        return round(ratio * 10.0, 1)
