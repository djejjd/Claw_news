from typing import Dict, List

from collectors.base import HotItem, Category


class Merger:
    """Aggregator: merges multi-source data, deduplicates by URL, sorts by final_score, takes top N per category."""

    def __init__(self, top_n: int = 5):
        self.top_n = top_n

    def merge(self, items: List[HotItem]) -> Dict[Category, List[HotItem]]:
        result: Dict[Category, List[HotItem]] = {
            "ai": [],
            "game": [],
            "device": [],
        }

        for category in result:
            cat_items = [item for item in items if item.category == category]
            deduped = self._dedup_by_url(cat_items)
            deduped.sort(key=lambda item: item.final_score, reverse=True)
            result[category] = deduped[: self.top_n]

        return result

    def _dedup_by_url(self, items: List[HotItem]) -> List[HotItem]:
        """URL dedup, keeps the item with highest source_score"""
        seen: Dict[str, HotItem] = {}
        for item in items:
            if not item.url:
                continue
            if item.url not in seen or item.source_score > seen[item.url].source_score:
                seen[item.url] = item
        return list(seen.values())
