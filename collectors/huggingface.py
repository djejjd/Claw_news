from typing import List

import httpx

from collectors.base import HotItem

HF_API_URL = "https://huggingface.co/api/daily_papers"


class HfDailyPapersCollector:
    """HuggingFace Daily Papers API collector. Sorted by community votes, takes top 10."""

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
        items = [self._parse_paper(p, max_votes) for p in papers[:10]]
        return items

    def _parse_paper(self, paper: dict, max_votes: int | None = None) -> HotItem:
        title = paper.get("title", "")
        paper_id = paper.get("paper", {}).get("id", "")
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
        )

    def _upvotes_to_score(self, upvotes: int, max_votes: int) -> float:
        """Normalize upvotes to 0-10. max_votes maps to 10, 0 maps to 0."""
        if max_votes <= 0:
            return 0.0
        ratio = upvotes / max_votes
        return round(ratio * 10.0, 1)
