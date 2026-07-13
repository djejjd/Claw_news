"""三阶段选材与唯一评分 — 纯函数模块。

Phase 1: today_guarantee    → AI 3 / 工具 2 / 游戏 2（仅今天）
Phase 2: historical_backfill → 同类不足时从历史候选补最低目标
Phase 3: today_competition   → 剩余名额仅从今天候选竞争

source_counts 跨三阶段累计，历史候选不进 Phase 3。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.content.source_policy import SourcePolicy
from app.content.time_policy import freshness_score, is_today
from app.pipeline.candidate import CandidateItem

_CATEGORY_MINIMUMS = {"ai": 3, "tool": 2, "game": 2}
_CATEGORY_ORDER = ("ai", "tool", "game")

# 单源多样性惩罚
_PENALTY = {0: 0.0, 1: -1.0, 2: -2.0, 3: -3.5}


# ---- 数据类 ----


@dataclass(frozen=True)
class SelectionEvidence:
    canonical_key: str
    phase: Literal["today_guarantee", "historical_backfill", "today_competition"]
    final_score: float
    diversity_penalty: float
    selection_score: float


@dataclass(frozen=True)
class SelectionResult:
    selected: list[CandidateItem]
    evidence: list[SelectionEvidence]
    category_counts: dict[str, int]


# ---- 评分 ----


def compute_final_score(
    item: CandidateItem,
    policy: SourcePolicy,
    now: datetime,
) -> float:
    """final_score = source_quality_weight + freshness_score"""
    from app.content.time_policy import candidate_effective_at

    # item.source_weight 优先（旧调用方可能显式传入），否则用 policy
    quality = getattr(item, "source_weight", None)
    if quality is None:
        quality = policy.quality_weight
    effective_at, _ = candidate_effective_at(item)
    if effective_at is not None:
        if effective_at.tzinfo is not None and now.tzinfo is None:
            effective_at = effective_at.replace(tzinfo=None)
        elif effective_at.tzinfo is None and now.tzinfo is not None:
            effective_at = effective_at.replace(tzinfo=now.tzinfo)
        age_hours = max((now - effective_at).total_seconds() / 3600, 0)
    else:
        age_hours = 0
    return round(quality + freshness_score(age_hours), 1)


def source_diversity_penalty(selected_count: int) -> float:
    """已入选 count 条时该源后续候选的额外扣分。"""
    if selected_count <= 0:
        return 0.0
    if selected_count >= 4:
        return -5.0
    return _PENALTY.get(selected_count, -5.0)


# ---- 选材 ----


def select_digest(
    items: list[CandidateItem],
    policies: dict[str, SourcePolicy],
    now: datetime,
    tz_name: str = "Asia/Shanghai",
    top_n: int = 10,
) -> SelectionResult:
    """三阶段选材，返回 SelectionResult。"""
    # 按 URL 去重（先算分，保留高分）
    for it in items:
        policy = policies.get(it.source, SourcePolicy(source=it.source))
        it.final_score = compute_final_score(it, policy, now)
    deduped: dict[str, CandidateItem] = {}
    for it in items:
        if not it.url:
            continue
        existing = deduped.get(it.url)
        if existing is None or it.final_score > existing.final_score:
            deduped[it.url] = it

    # 分离今日与历史
    today_items = []
    hist_items = []
    for it in deduped.values():
        # 使用 candidate_effective_at 统一日期解析（兼容 yyyy-mm-dd 和 ISO 格式）
        from app.content.time_policy import candidate_effective_at

        eff, _ = candidate_effective_at(it)
        if eff is not None:
            pub_dt = eff
        else:
            pub_dt = now  # fallback
        if is_today(pub_dt, now, tz_name):
            today_items.append(it)
        else:
            hist_items.append(it)

    selected = []
    evidence = []
    seen_urls: set[str] = set()
    source_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {c: 0 for c in _CATEGORY_ORDER}

    def _greedy_pick(pool, phase, target_per_cat=None, per_category=False):
        """通用贪心选材。per_category=True 时按分类顺序逐类选取。"""
        nonlocal selected, source_counts, evidence, seen_urls, category_counts
        remaining = [it for it in pool if it.url not in seen_urls]
        # 计算 selection_score
        scored = []
        for it in remaining:
            n = source_counts.get(it.source, 0)
            pen = source_diversity_penalty(n)
            scored.append((it, it.final_score + pen, pen))
        scored.sort(key=lambda x: (-x[1], -_pub_ts(x[0]), _ck(x[0])))

        if per_category:
            # 逐类选取
            for cat in _CATEGORY_ORDER:
                need = target_per_cat.get(cat, 0) if target_per_cat else 0
                cat_items = [
                    s for s in scored if s[0].category == cat and s[0].url not in seen_urls
                ]
                for it, sel_score, pen in cat_items:
                    if len(selected) >= top_n:
                        break
                    if category_counts[cat] >= need:
                        break
                    selected.append(it)
                    seen_urls.add(it.url)
                    src = it.source
                    source_counts[src] = source_counts.get(src, 0) + 1
                    category_counts[cat] += 1
                    ck2 = it.canonical_key or CandidateItem.make_canonical_key(it.url or "")
                    evidence.append(
                        SelectionEvidence(
                            canonical_key=ck2,
                            phase=phase,
                            final_score=it.final_score,
                            diversity_penalty=pen,
                            selection_score=sel_score,
                        )
                    )
        else:
            for it, sel_score, pen in scored:
                if len(selected) >= top_n:
                    break
                cat = it.category if it.category in _CATEGORY_ORDER else "ai"
                need = target_per_cat.get(cat) if target_per_cat else None
                if need is not None and category_counts[cat] >= need:
                    continue
                selected.append(it)
                seen_urls.add(it.url)
                src = it.source
                source_counts[src] = source_counts.get(src, 0) + 1
                category_counts[cat] += 1
                ck = it.canonical_key or CandidateItem.make_canonical_key(it.url or "")
                evidence.append(
                    SelectionEvidence(
                        canonical_key=ck,
                        phase=phase,
                        final_score=it.final_score,
                        diversity_penalty=pen,
                        selection_score=sel_score,
                    )
                )

    # Phase 1: 今日保底（逐类选取，保证先满足 AI→工具→游戏 最低目标）
    _greedy_pick(today_items, "today_guarantee", _CATEGORY_MINIMUMS, per_category=True)

    # Phase 2: 历史补位（逐类选取）
    if any(category_counts[c] < _CATEGORY_MINIMUMS[c] for c in _CATEGORY_ORDER):
        _greedy_pick(hist_items, "historical_backfill", _CATEGORY_MINIMUMS, per_category=True)

    # Phase 3: 今日自由竞争
    _greedy_pick(today_items, "today_competition")

    # 按 final_score 降序排
    selected.sort(key=lambda x: (-getattr(x, "final_score", 0), _ck(x)))
    return SelectionResult(
        selected=selected,
        evidence=sorted(evidence, key=lambda e: (-e.final_score, e.canonical_key)),
        category_counts=category_counts,
    )


# ---- 排序辅助 ----


def _pub_ts(item: CandidateItem) -> float:
    """返回 published_at 的 timestamp 用于排序，新者更大。"""
    pub = item.published_at or ""
    try:
        return datetime.fromisoformat(pub).timestamp()
    except (ValueError, TypeError):
        return 0.0


def _ck(item: CandidateItem) -> str:
    """返回 canonical_key 用于字典序排序。"""
    return item.canonical_key or CandidateItem.make_canonical_key(item.url or "")
