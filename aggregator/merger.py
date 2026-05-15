from typing import Dict, List

from collectors.base import HotItem, Category, time_modifier


def position_score(pos: int) -> float:
    """RSS 排位 → 第1=10.0，线性递减至第10=5.5"""
    pos = max(1, min(pos, 10))
    return 10.0 - (pos - 1) * 0.5


def compute_source_score(item: HotItem, position: int = 5, period: str = "morning") -> float:
    """三维评分：HF/TapTap 保持原始分，RSS 源 = position + keyword + time_modifier"""
    if item.source in ("huggingface", "taptap"):
        return item.source_score
    pos_s = position_score(position)
    kw_s = 1.0 if item.keyword_hit else 0.0
    tm_s = time_modifier(item.pub_date, period)
    return round(pos_s + kw_s + tm_s, 1)


class Merger:
    """聚合器：三维评分 + 关键词保底竞争，每分类 5 条"""

    def __init__(self, top_n: int = 5):
        self.top_n = top_n

    def merge(self, items: List[HotItem], period: str = "morning") -> Dict[Category, List[HotItem]]:
        result: Dict[Category, List[HotItem]] = {"ai": [], "game": [], "device": []}

        for category in result:
            cat_items = [i for i in items if i.category == category]
            if not cat_items:
                continue

            # Dedup by URL, keep higher score
            deduped = self._dedup_by_url(cat_items)

            # Group by source
            sources: Dict[str, List[HotItem]] = {}
            for item in deduped:
                sources.setdefault(item.source, []).append(item)

            # Score items: RSS uses 3D (position+keyword+time_modifier), HF/TapTap keep original
            for src, src_items in sources.items():
                for i, item in enumerate(src_items):
                    item.source_score = compute_source_score(item, i + 1, period)

            # Sort each source group by source_score descending
            for src_items in sources.values():
                src_items.sort(key=lambda x: x.source_score, reverse=True)

            # Step 1: 关键词保底 — 每源至少 1 条
            selected: List[HotItem] = []
            for src, src_items in sources.items():
                kw_items = [i for i in src_items if i.keyword_hit]
                selected.append(kw_items[0] if kw_items else src_items[0])

            # Step 2: 全量竞争 — 剩余 3 条
            selected_urls = {i.url for i in selected}
            remaining = [i for i in deduped if i.url not in selected_urls]
            remaining.sort(key=lambda x: x.source_score, reverse=True)
            needed = max(0, self.top_n - len(selected))
            selected.extend(remaining[:needed])

            # Step 3: 最终排序
            selected.sort(key=lambda x: x.source_score, reverse=True)
            result[category] = selected[:self.top_n]

        return result

    def _dedup_by_url(self, items: List[HotItem]) -> List[HotItem]:
        seen: Dict[str, HotItem] = {}
        for item in items:
            if not item.url:
                continue
            if item.url not in seen or item.source_score > seen[item.url].source_score:
                seen[item.url] = item
        return list(seen.values())
