from typing import Dict, List, Union

from collectors.base import Category, HotItem, LegacyCategory, time_modifier, to_legacy_category

# =============================================================================
# Phase 4: 统一评分常量
# =============================================================================

SOURCE_WEIGHTS = {
    "huggingface": 4.0,
    "qbitai": 3.0,
    # 其他进入 ai_only 发布范围的 RSS AI 垂类来源默认 3.0
}
DEFAULT_AI_SOURCE_WEIGHT = 3.0
DEFAULT_OTHER_SOURCE_WEIGHT = 2.0

TOPIC_WEIGHTS = {
    "model_release": 3.0,
    "agent_workflow": 2.5,
    "developer_tooling": 2.0,
    "research_benchmark": 2.0,
    "infrastructure": 1.5,
    "application_case": 1.0,
}
DEFAULT_TOPIC_WEIGHT = 1.0
KEYWORD_BONUS = 0.5  # 固定布尔加分


def compute_final_score(item) -> float:
    """统一评分：source_weight + topic_weight + keyword_bonus + time_modifier

    接受 CandidateItem 或任何有 topic/source_weight 等属性的对象。
    """
    sw = getattr(item, "source_weight", None)
    if sw is None:
        sw = SOURCE_WEIGHTS.get(getattr(item, "source", ""), DEFAULT_AI_SOURCE_WEIGHT)
    tw = getattr(item, "topic_weight", None)
    if tw is None:
        tw = TOPIC_WEIGHTS.get(getattr(item, "topic", ""), DEFAULT_TOPIC_WEIGHT)
    kb = (
        KEYWORD_BONUS
        if getattr(item, "keyword_bonus", None) or getattr(item, "keyword_hit", False)
        else 0.0
    )
    pub_date = getattr(item, "pub_date", None) or getattr(item, "published_at", "")
    tm = time_modifier(pub_date, "morning")
    return round(sw + tw + kb + tm, 1)


# =============================================================================
# Legacy scoring functions (保留向后兼容)
# =============================================================================


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


# =============================================================================
# Merger
# =============================================================================


class Merger:
    """聚合器：三维评分 + 关键词保底竞争，每分类 5 条。

    支持两套评分模式：
    - use_new_scoring=False（默认）：现有行为，按 category 分组 + 每源保底
    - use_new_scoring=True：统一 compute_final_score，全量竞争 TopN
    """

    def __init__(self, top_n: int = 5):
        self.top_n = top_n

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def merge(
        self,
        items: List,
        period: str = "morning",
        use_new_scoring: bool = False,
    ) -> Union[Dict[Category, List[HotItem]], List]:
        """聚合入口：根据 use_new_scoring 选择评分路径。

        use_new_scoring=False（默认）：保持现有行为完全不变。
        use_new_scoring=True：使用 compute_final_score()，不做每源保底，
        直接返回排序后的 TopN 列表（不分 category）。
        """
        if not use_new_scoring:
            return self._merge_legacy(items, period)

        # ---- 新评分路径 ----
        # Pre-compute final_score so dedup can use it
        for item in items:
            item.final_score = compute_final_score(item)
        deduped = self._dedup_by_url(items)
        deduped.sort(key=lambda x: x.final_score, reverse=True)
        return deduped[: self.top_n]

    # ------------------------------------------------------------------
    # Legacy merge (保留原有行为)
    # ------------------------------------------------------------------

    def _merge_legacy(
        self, items: List[HotItem], period: str = "morning"
    ) -> Dict[LegacyCategory, List[HotItem]]:
        result: Dict[LegacyCategory, List[HotItem]] = {"ai": [], "game": [], "device": []}

        for category in result:
            cat_items = [i for i in items if to_legacy_category(i.category) == category]
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
            result[category] = selected[: self.top_n]

        return result

    # ------------------------------------------------------------------
    # Dedup
    # ------------------------------------------------------------------

    def _dedup_by_url(self, items: List) -> List:
        """按 URL 去重，保留高分项。兼容 HotItem 和 CandidateItem。"""
        seen: Dict[str, object] = {}
        for item in items:
            url = getattr(item, "url", "")
            if not url:
                continue
            score = getattr(item, "final_score", None) or getattr(item, "source_score", 0)
            if url not in seen:
                seen[url] = item
            else:
                seen_score = getattr(seen[url], "final_score", None) or getattr(
                    seen[url], "source_score", 0
                )
                if score > seen_score:
                    seen[url] = item
        return list(seen.values())
