"""GitHub 项目综合评分、曝光惩罚、推荐理由。

纯规则引擎，不依赖 LLM，所有输出可解释。
"""

from __future__ import annotations

import math
from datetime import date, timedelta

from collectors.github import GitHubRepoItem


# ---- 活跃度评分 ----

def _activity_score(item: GitHubRepoItem) -> float:
    """基于 pushed_at 的活跃度，越近越高分。

    公式：3.0 * exp(-days_since_push / 30)
    - 当天 push: ~3.0
    - 7 天前: ~2.4
    - 30 天前: ~1.1
    - 90 天前: ~0.15
    """
    days = _days_since(item.pushed_at)
    if days is None:
        return 0.0
    return round(3.0 * math.exp(-days / 30), 2)


# ---- 热度/质量评分 ----

def _popularity_score(item: GitHubRepoItem) -> float:
    """综合 stars / forks / watchers，对数压缩防止头部垄断。

    公式：log10(stars+1)*1.0 + log10(forks+1)*0.5 + log10(watchers+1)*0.3
    """
    s = math.log10(item.stars + 1) * 1.0
    f = math.log10(item.forks + 1) * 0.5
    w = math.log10(item.watchers + 1) * 0.3
    return round(s + f + w, 2)


# ---- 相关性评分 ----

_RELEVANT_TOPICS = frozenset({"llm", "agent", "ai-tools", "machine-learning"})
_RELEVANT_KEYWORDS = frozenset({"ai agent", "llm", "developer tooling", "game ai"})

def _relevance_score(item: GitHubRepoItem) -> float:
    """topic 命中 + keyword 命中。

    公式：topic_hits * 0.5 + keyword_hits * 0.3
    """
    t = len(set(item.matched_topics) & _RELEVANT_TOPICS) * 0.5
    k = len(set(item.matched_keywords) & _RELEVANT_KEYWORDS) * 0.3
    return round(t + k, 2)


# ---- 曝光惩罚 ----

def _exposure_penalty(item: GitHubRepoItem, exposure_dates: dict[str, date]) -> float:
    """基于最近一次曝光日期的惩罚。

    - 1 天内: -3.0
    - 3 天内: -1.5
    - 7 天内: -0.5
    - 超过 7 天: 0
    """
    last_exposure = exposure_dates.get(item.full_name)
    if last_exposure is None:
        return 0.0
    days = (date.today() - last_exposure).days
    if days <= 1:
        return -3.0
    if days <= 3:
        return -1.5
    if days <= 7:
        return -0.5
    return 0.0


# ---- 推荐理由 ----

def _recommendation_reason(item: GitHubRepoItem) -> str:
    """基于结构化信号生成推荐理由，纯规则。"""
    reasons = []

    # 活跃度
    pushed_days = _days_since(item.pushed_at)
    if pushed_days is not None and pushed_days <= 3:
        reasons.append("近3天活跃更新")

    # 热度
    if item.stars >= 5000:
        reasons.append("社区热度高")
    elif item.stars >= 1000:
        reasons.append("关注度上升")

    # 新项目
    created_days = _days_since(item.created_at)
    if created_days is not None and created_days <= 30 and item.stars >= 100:
        reasons.append("新项目快速增长")

    # 领域标签
    if "agent" in item.matched_topics or _keyword_match(item, "ai agent"):
        reasons.append("AI Agent 工具链")
    elif "llm" in item.matched_topics or _keyword_match(item, "llm"):
        reasons.append("大模型生态")
    elif _keyword_match(item, "developer tooling"):
        reasons.append("开发者工具")
    elif _keyword_match(item, "game ai"):
        reasons.append("游戏AI")

    if not reasons:
        reasons.append("值得关注")

    return " · ".join(reasons[:2])


def _keyword_match(item: GitHubRepoItem, kw: str) -> bool:
    return kw in (item.description or "").lower() or kw in item.full_name.lower()


def _days_since(date_str: str) -> int | None:
    """计算 date_str 距今天数，解析失败返回 None。"""
    if not date_str:
        return None
    try:
        d = date.fromisoformat(date_str[:10])
        return (date.today() - d).days
    except (ValueError, TypeError):
        return None


# ---- Public API ----

def rank_and_recommend(
    candidates: list[GitHubRepoItem],
    exposure_dates: dict[str, date],
    top_n: int = 3,
) -> list[dict]:
    """对候选评分、曝光惩罚、排序，输出 topN 及推荐理由。

    Args:
        candidates: 候选项目列表
        exposure_dates: {full_name: last_exposure_date}
        top_n: 返回前几名

    Returns:
        [{full_name, recommendation, score, activity, popularity, relevance, penalty}, ...]
    """
    # 最低质量标准：过滤明显 spam（0-star fork/spam）
    candidates = [c for c in candidates if c.stars >= 10]
    scored = []
    for item in candidates:
        activity = _activity_score(item)
        popularity = _popularity_score(item)
        relevance = _relevance_score(item)
        penalty = _exposure_penalty(item, exposure_dates)
        final = round(activity + popularity + relevance + penalty, 2)

        scored.append({
            "item": item,
            "final_score": final,
            "activity": activity,
            "popularity": popularity,
            "relevance": relevance,
            "penalty": penalty,
            "recommendation": _recommendation_reason(item),
        })

    scored.sort(key=lambda x: x["final_score"], reverse=True)
    return scored[:top_n]
