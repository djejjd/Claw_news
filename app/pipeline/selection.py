"""三阶段选材与唯一评分 — 纯函数模块。

Phase 1: today_guarantee    → AI 3 / 工具 2 / 游戏 2（仅今天）
Phase 2: historical_backfill → 同类不足时从历史候选补最低目标
Phase 3: today_competition   → 剩余名额仅从今天候选竞争

source_counts 跨三阶段累计，历史候选不进 Phase 3。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal
from urllib.parse import unquote, urlparse

from app.content.source_policy import SourcePolicy, source_selection_cap
from app.content.time_policy import freshness_score, is_today
from app.pipeline.candidate import CandidateItem

_CATEGORY_MINIMUMS = {"ai": 3, "tool": 2, "game": 2, "digital": 0}
_CATEGORY_ORDER = ("ai", "tool", "game", "digital")

# 单源多样性惩罚
_PENALTIES = {
    "linear": {0: 0.0, 1: -1.0, 2: -2.0, 3: -3.5, 4: -5.0},
    "exponential": {0: 0.0, 1: -1.0, 2: -3.0, 3: -6.0, 4: -10.0},
}


# ---- 数据类 ----


@dataclass(frozen=True)
class SelectionEvidence:
    canonical_key: str
    phase: Literal[
        "today_guarantee",
        "historical_backfill",
        "today_competition",
        "historical_competition",
        "soft_cap_backfill",
    ]
    final_score: float
    diversity_penalty: float
    selection_score: float
    soft_source_cap_exceeded: bool = False


@dataclass(frozen=True)
class TopicClusterRound:
    """一次聚类重选的真实轮次结果，包含最终无排除的收敛轮。"""

    selection_round: int
    available_count: int
    selected_before_count: int
    excluded_count: int
    cumulative_excluded_count: int
    converged: bool


@dataclass(frozen=True)
class SelectionResult:
    selected: list[CandidateItem]
    evidence: list[SelectionEvidence]
    category_counts: dict[str, int]
    cluster_rounds: tuple[TopicClusterRound, ...] = ()


@dataclass(frozen=True)
class TopicClusterEvent:
    selection_round: int
    winner_canonical_key: str
    loser_canonical_key: str
    title_similarity: float
    url_similarity: float
    trigger_edges: tuple[tuple[str, str, float, float], ...]
    final_score: float
    selection_score: float
    round_evidence: tuple[SelectionEvidence, ...] = ()


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


def source_diversity_penalty(selected_count: int, profile: str = "linear") -> float:
    """已入选 count 条时该源后续候选的额外扣分。"""
    if profile not in _PENALTIES:
        raise ValueError("SELECTION_DIVERSITY_PENALTY_PROFILE must be linear or exponential")
    if selected_count <= 0:
        return 0.0
    penalties = _PENALTIES[profile]
    return penalties.get(selected_count, penalties[4])


# ---- 选材 ----


def select_digest(
    items: list[CandidateItem],
    policies: dict[str, SourcePolicy],
    now: datetime,
    tz_name: str = "Asia/Shanghai",
    top_n: int = 10,
    diversity_penalty_profile: str = "linear",
) -> SelectionResult:
    """三阶段选材，返回 SelectionResult。"""
    if diversity_penalty_profile not in _PENALTIES:
        raise ValueError("SELECTION_DIVERSITY_PENALTY_PROFILE must be linear or exponential")
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

    def _greedy_pick(pool, phase, target_per_cat=None, per_category=False, allow_soft_cap=False):
        """通用贪心选材。per_category=True 时按分类顺序逐类选取。"""
        nonlocal selected, source_counts, evidence, seen_urls, category_counts

        def scored_candidates(category: str | None = None):
            scored = []
            for it in pool:
                if it.url in seen_urls or (category is not None and it.category != category):
                    continue
                n = source_counts.get(it.source, 0)
                policy = policies.get(it.source, SourcePolicy(source=it.source))
                cap, hard_cap = source_selection_cap(policy)
                if n >= cap and (hard_cap or not allow_soft_cap):
                    continue
                pen = source_diversity_penalty(n, diversity_penalty_profile)
                scored.append((it, it.final_score + pen, pen))
            return sorted(scored, key=lambda x: (-x[1], -_pub_ts(x[0]), _ck(x[0])))

        def add_item(it, sel_score, pen, phase_name: str) -> None:
            cat = it.category if it.category in _CATEGORY_ORDER else "ai"
            selected.append(it)
            seen_urls.add(it.url)
            src = it.source
            policy = policies.get(src, SourcePolicy(source=src))
            cap, _ = source_selection_cap(policy)
            soft_cap_exceeded = allow_soft_cap and source_counts.get(src, 0) >= cap
            source_counts[src] = source_counts.get(src, 0) + 1
            category_counts[cat] += 1
            ck = it.canonical_key or CandidateItem.make_canonical_key(it.url or "")
            evidence.append(
                SelectionEvidence(
                    canonical_key=ck,
                    phase=phase_name,
                    final_score=it.final_score,
                    diversity_penalty=pen,
                    selection_score=sel_score,
                    soft_source_cap_exceeded=soft_cap_exceeded,
                )
            )

        if per_category:
            # 逐类选取
            for cat in _CATEGORY_ORDER:
                need = target_per_cat.get(cat, 0) if target_per_cat else 0
                while len(selected) < top_n and category_counts[cat] < need:
                    candidates = scored_candidates(cat)
                    if not candidates:
                        break
                    it, sel_score, pen = candidates[0]
                    add_item(it, sel_score, pen, phase)
        else:
            while len(selected) < top_n:
                candidates = scored_candidates()
                if not candidates:
                    break
                it, sel_score, pen = candidates[0]
                add_item(it, sel_score, pen, phase)

    # Phase 1: 今日保底（逐类选取，保证先满足 AI→工具→游戏 最低目标）
    _greedy_pick(today_items, "today_guarantee", _CATEGORY_MINIMUMS, per_category=True)

    # Phase 2: 历史补位（先补分类最低目标）
    if any(category_counts[c] < _CATEGORY_MINIMUMS[c] for c in _CATEGORY_ORDER):
        _greedy_pick(hist_items, "historical_backfill", _CATEGORY_MINIMUMS, per_category=True)

    # Phase 3: 今日自由竞争
    _greedy_pick(today_items, "today_competition")

    # Phase 4: 今日不足时，用剩余历史候选按质量和新鲜度补齐总量。
    if len(selected) < top_n:
        _greedy_pick(hist_items, "historical_competition")

    # Phase 5: 只有总量仍不足时，非快讯来源才可突破 3 条软上限。
    if len(selected) < top_n:
        _greedy_pick(today_items + hist_items, "soft_cap_backfill", allow_soft_cap=True)

    # 按 final_score 降序排
    selected.sort(key=lambda x: (-getattr(x, "final_score", 0), _ck(x)))
    return SelectionResult(
        selected=selected,
        evidence=sorted(evidence, key=lambda e: (-e.final_score, e.canonical_key)),
        category_counts=category_counts,
    )


def select_digest_with_topic_clustering(
    items: list[CandidateItem],
    policies: dict[str, SourcePolicy],
    now: datetime,
    tz_name: str = "Asia/Shanghai",
    top_n: int = 10,
    diversity_penalty_profile: str = "linear",
    *,
    enabled: bool = False,
    threshold: float = 0.7,
    max_rounds: int = 10,
) -> tuple[SelectionResult, list[TopicClusterEvent]]:
    """Select, exclude duplicate topic-cluster losers, and reselect to convergence."""
    if not enabled:
        return (
            select_digest(items, policies, now, tz_name, top_n, diversity_penalty_profile),
            [],
        )
    if not 0 < threshold <= 1 or max_rounds <= 0:
        raise ValueError("topic cluster threshold and max rounds must be positive")

    excluded: set[str] = set()
    events: list[TopicClusterEvent] = []
    rounds: list[TopicClusterRound] = []
    for round_number in range(1, max_rounds + 1):
        available = [item for item in items if _ck(item) not in excluded]
        result = select_digest(available, policies, now, tz_name, top_n, diversity_penalty_profile)
        evidence_by_key = {event.canonical_key: event for event in result.evidence}
        edges = _topic_similarity_edges(result.selected, threshold)
        if not edges:
            rounds.append(
                TopicClusterRound(
                    selection_round=round_number,
                    available_count=len(available),
                    selected_before_count=len(result.selected),
                    excluded_count=0,
                    cumulative_excluded_count=len(excluded),
                    converged=True,
                )
            )
            return replace(result, cluster_rounds=tuple(rounds)), events
        losers = set()
        selected_by_key = {_ck(item): item for item in result.selected}
        for component_keys in _components(edges):
            component = [selected_by_key[key] for key in component_keys]
            component_edges = tuple(
                (_ck(left), _ck(right), title_similarity, url_similarity)
                for left, right, title_similarity, url_similarity in edges
                if _ck(left) in component_keys and _ck(right) in component_keys
            )
            winner = sorted(
                component,
                key=lambda item: (
                    -evidence_by_key[_ck(item)].selection_score,
                    -_pub_ts(item),
                    _ck(item),
                ),
            )[0]
            for item in component:
                if item is not winner and _ck(item) not in losers:
                    losers.add(_ck(item))
                    direct_edge = next(
                        (
                            edge
                            for edge in component_edges
                            if _ck(item) in edge[:2] and _ck(winner) in edge[:2]
                        ),
                        component_edges[0],
                    )
                    events.append(
                        TopicClusterEvent(
                            round_number,
                            _ck(winner),
                            _ck(item),
                            direct_edge[2],
                            direct_edge[3],
                            component_edges,
                            item.final_score,
                            evidence_by_key[_ck(item)].selection_score,
                            tuple(result.evidence),
                        )
                    )
        if not losers:
            rounds.append(
                TopicClusterRound(
                    selection_round=round_number,
                    available_count=len(available),
                    selected_before_count=len(result.selected),
                    excluded_count=0,
                    cumulative_excluded_count=len(excluded),
                    converged=True,
                )
            )
            return replace(result, cluster_rounds=tuple(rounds)), events
        excluded.update(losers)
        rounds.append(
            TopicClusterRound(
                selection_round=round_number,
                available_count=len(available),
                selected_before_count=len(result.selected),
                excluded_count=len(losers),
                cumulative_excluded_count=len(excluded),
                converged=False,
            )
        )
    raise RuntimeError("topic_cluster_non_convergent")


def reselect_digest_after_llm_relevance(
    items: list[CandidateItem],
    policies: dict[str, SourcePolicy],
    now: datetime,
    *,
    excluded_canonical_keys: set[str],
    initially_scored_keys: set[str],
    tz_name: str = "Asia/Shanghai",
    top_n: int = 10,
    diversity_penalty_profile: str = "linear",
    topic_cluster_enabled: bool = False,
    topic_cluster_threshold: float = 0.7,
    topic_cluster_max_rounds: int = 10,
) -> tuple[SelectionResult, list[TopicClusterEvent], list[dict]]:
    """移除低相关初选项后，按完整既有约束从候选池重新选材。"""
    available = [item for item in items if _ck(item) not in excluded_canonical_keys]
    result, cluster_events = select_digest_with_topic_clustering(
        available,
        policies,
        now,
        tz_name,
        top_n,
        diversity_penalty_profile,
        enabled=topic_cluster_enabled,
        threshold=topic_cluster_threshold,
        max_rounds=topic_cluster_max_rounds,
    )
    backfills = [
        {
            "event": "llm_relevance_backfill",
            "canonical_key": _ck(item),
            "relevance": None,
            "relevance_source": "not_scored_backfill",
        }
        for item in result.selected
        if _ck(item) not in initially_scored_keys
    ]
    return result, cluster_events, backfills


def _topic_similarity_edges(items: list[CandidateItem], threshold: float):
    edges = []
    for index, left in enumerate(items):
        if not left.topic or left.topic.startswith("general_"):
            continue
        for right in items[index + 1 :]:
            if left.category != right.category or left.topic != right.topic:
                continue
            title_similarity = _jaccard(_tokens(left.title), _tokens(right.title))
            url_similarity = _jaccard(_url_tokens(left.url), _url_tokens(right.url))
            if title_similarity >= threshold or (
                title_similarity >= 0.35 and url_similarity >= threshold
            ):
                edges.append((left, right, title_similarity, url_similarity))
    return edges


def _components(edges):
    graph = {}
    for left, right, *_ in edges:
        left_key, right_key = _ck(left), _ck(right)
        graph.setdefault(left_key, set()).add(right_key)
        graph.setdefault(right_key, set()).add(left_key)
    result = []
    while graph:
        start = min(graph)
        stack, component = [start], set()
        while stack:
            item = stack.pop()
            if item in component:
                continue
            component.add(item)
            stack.extend(reversed(sorted(graph.get(item, set()))))
        for item in sorted(component):
            graph.pop(item, None)
        result.append(component)
    return sorted(result, key=lambda component: min(component))


def _tokens(value: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    tokens = set(re.findall(r"[a-z0-9]+", normalized))
    for chunk in re.findall(r"[\u4e00-\u9fff]+", normalized):
        tokens.update(chunk[index : index + 2] for index in range(max(len(chunk) - 1, 0)))
    return tokens


def _url_tokens(url: str) -> set[str]:
    return _tokens(unquote(urlparse(url).path).replace("/", " "))


def _jaccard(left: set[str], right: set[str]) -> float:
    return len(left & right) / len(left | right) if left and right else 0.0


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
