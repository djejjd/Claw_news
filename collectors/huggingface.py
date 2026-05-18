import asyncio
from datetime import date
from typing import List

from curl_cffi import requests as curl_requests
from deep_translator import GoogleTranslator

from collectors.base import HotItem

HF_API_URL = "https://huggingface.co/api/daily_papers"

_translate_semaphore = asyncio.Semaphore(3)


async def _translate_to_chinese(text: str) -> str:
    """Translate English text to Chinese via Google Translate (free, no API key)."""
    if not text or not text.strip():
        return text
    async with _translate_semaphore:
        try:
            result = await asyncio.to_thread(
                GoogleTranslator(source="auto", target="zh-CN").translate, text
            )
            return result if result else text
        except Exception:
            return text


class HfDailyPapersCollector:
    """HuggingFace Daily Papers API collector. Uses curl_cffi for TLS fingerprint."""

    def __init__(self, fetch_count: int = 10, client=None):
        self._fetch_count = fetch_count
        self._client = client

    async def collect(self) -> List[HotItem]:
        if self._client is not None:
            resp = await self._client.get(HF_API_URL, timeout=15.0)
            resp.raise_for_status()
            papers = resp.json()
        else:
            session = curl_requests.AsyncSession(impersonate="chrome131")
            try:
                resp = await session.get(HF_API_URL, timeout=15.0)
                resp.raise_for_status()
                papers = resp.json()
            finally:
                await session.close()

        max_votes = max((p.get("upvotes", 0) for p in papers), default=1)
        papers.sort(key=lambda p: p.get("upvotes", 0), reverse=True)
        items = [self._parse_paper(p, max_votes) for p in papers[: self._fetch_count]]

        # 并发翻译所有摘要
        translations = await asyncio.gather(
            *[_translate_to_chinese(item.summary) for item in items],
            return_exceptions=True,
        )
        for item, trans in zip(items, translations):
            if isinstance(trans, str):
                item.summary = trans

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
