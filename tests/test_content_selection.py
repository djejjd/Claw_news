"""Task 5: 三阶段选材与唯一评分 — 失败测试。"""

from datetime import datetime, timedelta

import pytest

from app.content.source_policy import SourcePolicy
from app.pipeline.candidate import CandidateItem

_TODAY = "2026-07-11"
_NOW = datetime.fromisoformat("2026-07-11T09:00:00+08:00")
_TZ = "Asia/Shanghai"


def _make_item(**kwargs) -> CandidateItem:
    data = {
        "title": "T", "url": "https://x.test", "summary": "S",
        "source": "qbitai", "category": "ai",
        "published_at": f"{_TODAY}T08:00:00+08:00",
        "canonical_key": "",
    }
    data.update(kwargs)
    if not data["canonical_key"]:
        data["canonical_key"] = CandidateItem.make_canonical_key(data["url"])
    return CandidateItem(**data)


# ======================== 评分与 penalty ========================


def test_module_importable():
    """模块可导入 — 实现前应失败。"""
    from app.pipeline.selection import (  # noqa: F401
        SelectionEvidence,
        SelectionResult,
        compute_final_score,
        select_digest,
        source_diversity_penalty,
    )


def test_final_score_is_quality_plus_freshness():
    """final_score = quality_weight + freshness_score"""
    from app.pipeline.selection import compute_final_score

    now = datetime.fromisoformat("2026-07-11T09:00:00+08:00")
    item = _make_item(
        source="qbitai", category="ai",
        published_at="2026-07-10T03:00:00+08:00",
    )
    policy = SourcePolicy("qbitai", "vertical", 48, 3.5, "standard")
    # 30h ago → freshness=1.5, quality=3.5 → 5.0
    assert compute_final_score(item, policy, now) == 5.0


@pytest.mark.parametrize(("count", "penalty"), [
    (0, 0.0), (1, -1.0), (2, -2.0), (3, -3.5), (4, -5.0), (9, -5.0),
])
def test_diversity_penalty(count, penalty):
    """单源惩罚映射与设计一致。"""
    from app.pipeline.selection import source_diversity_penalty

    assert source_diversity_penalty(count) == penalty


# ======================== 三阶段选材 ========================


def build_selection_fixture(now):
    """今日 AI 2、工具 2、游戏 2，历史 AI 1、历史高分工具 1"""
    today = now.strftime("%Y-%m-%d")
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")

    items = [
        # 今日
        _make_item(title="AI-今日1", url="https://ai1.test", source="qbitai",
                   category="ai", published_at=f"{today}T08:00:00+08:00",
                   canonical_key="ai-today-1"),
        _make_item(title="AI-今日2", url="https://ai2.test", source="leiphone",
                   category="ai", published_at=f"{today}T07:00:00+08:00",
                   canonical_key="ai-today-2"),
        _make_item(title="工具-今日1", url="https://t1.test", source="sspai",
                   category="tool", published_at=f"{today}T08:00:00+08:00"),
        _make_item(title="工具-今日2", url="https://t2.test", source="appinn",
                   category="tool", published_at=f"{today}T08:00:00+08:00"),
        _make_item(title="游戏-今日1", url="https://g1.test", source="yystv",
                   category="game", published_at=f"{today}T08:00:00+08:00"),
        _make_item(title="游戏-今日2", url="https://g2.test", source="gcores",
                   category="game", published_at=f"{today}T08:00:00+08:00"),
        # 历史
        _make_item(title="AI-历史1", url="https://old-ai.test", source="qbitai",
                   category="ai", published_at=f"{yesterday}T12:00:00+08:00",
                   canonical_key="old-ai-1"),
        _make_item(title="工具-历史高分", url="https://old-tool.test", source="ithome",
                   category="tool", published_at=f"{yesterday}T12:00:00+08:00",
                   canonical_key="old-high-tool"),
    ]
    policies = {
        s: SourcePolicy(s, "vertical", 48, 3.0, "standard")
        for s in ["qbitai", "leiphone", "sspai", "appinn", "yystv", "gcores", "ithome"]
    }
    return items, policies


def build_cross_phase_same_source_fixture(now):
    """同一 source 分别在 Phase 1、Phase 2、Phase 3 入选。
    source=same_src, 今日 AI=2 条 + 历史 AI=1 条 + 今日自由竞争=1 条（也是 same_src）"""
    today = now.strftime("%Y-%m-%d")
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")

    items = [
        # Phase 1: 今日保底
        _make_item(title="same-今日AI1", url="https://same-p1.test", source="same_src",
                   category="ai", published_at=f"{today}T09:00:00+08:00",
                   canonical_key="same-p1"),
        # Phase 2: 历史补位（同类 AI 不足时）
        _make_item(title="same-历史AI", url="https://same-p2.test", source="same_src",
                   category="ai", published_at=f"{yesterday}T12:00:00+08:00",
                   canonical_key="same-p2"),
        # Phase 3: 今日竞争（也是 same_src）
        _make_item(title="same-今日AI2", url="https://same-p3.test", source="same_src",
                   category="ai", published_at=f"{today}T10:00:00+08:00",
                   canonical_key="same-p3"),
        # 其他类确保够选
        _make_item(title="工具-今日1", url="https://t1.test", source="sspai",
                   category="tool", published_at=f"{today}T08:00:00+08:00"),
        _make_item(title="工具-今日2", url="https://t2.test", source="appinn",
                   category="tool", published_at=f"{today}T08:00:00+08:00"),
        _make_item(title="游戏-今日1", url="https://g1.test", source="yystv",
                   category="game", published_at=f"{today}T08:00:00+08:00"),
        _make_item(title="游戏-今日2", url="https://g2.test", source="gcores",
                   category="game", published_at=f"{today}T08:00:00+08:00"),
    ]
    policies = {
        s: SourcePolicy(s, "vertical", 48, 3.0, "standard")
        for s in ["same_src", "sspai", "appinn", "yystv", "gcores"]
    }
    return items, policies


def test_historical_items_only_fill_category_deficit():
    """历史候选用入 Phase 2 补最低目标，不进 Phase 3。"""
    from app.pipeline.selection import select_digest

    now = _NOW
    items, policies = build_selection_fixture(now)
    result = select_digest(items, policies, now)

    phases = {e.canonical_key: e.phase for e in result.evidence}
    assert phases.get("old-ai-1") == "historical_backfill"
    # 工具类今日已够 2 条，历史高分工具不应入选
    selected_keys = {x.canonical_key for x in result.selected}
    assert "old-high-tool" not in selected_keys


def test_source_counts_accumulate_across_phases():
    """同一 source 在三阶段中累计计数，penalty 递增。"""
    from app.pipeline.selection import select_digest

    now = _NOW
    items, policies = build_cross_phase_same_source_fixture(now)
    result = select_digest(items, policies, now)

    same_evidence = [
        e for e in result.evidence
        if e.canonical_key.startswith("same-p")
    ]
    # 至少 1 条 same_src 入选（因多样性惩罚可能被竞争挤掉部分）
    assert len(same_evidence) >= 1
    # source_counts 跨阶段累计：penalty 不为 0 说明之前的入选被正确计数
    if len(same_evidence) >= 2:
        penalties = sorted(e.diversity_penalty for e in same_evidence)
        assert penalties != [0.0, 0.0]  # 不全是无惩罚


def test_category_minimums_3_2_2():
    """今日充足时分类最低目标 AI 3、工具 2、游戏 2。"""
    from app.pipeline.selection import select_digest

    now = _NOW
    # 需要足够多候选才能测 3/2/2
    today = now.strftime("%Y-%m-%d")
    items = [
        _make_item(title=f"AI-{i}", url=f"https://ai{i}.test",
                   source=f"src-ai{i}", category="ai",
                   published_at=f"{today}T08:00:00+08:00")
        for i in range(5)
    ] + [
        _make_item(title=f"工具-{i}", url=f"https://t{i}.test",
                   source=f"src-t{i}", category="tool",
                   published_at=f"{today}T08:00:00+08:00")
        for i in range(5)
    ] + [
        _make_item(title=f"游戏-{i}", url=f"https://g{i}.test",
                   source=f"src-g{i}", category="game",
                   published_at=f"{today}T08:00:00+08:00")
        for i in range(5)
    ]
    policies = {}
    for i in range(5):
        policies[f"src-ai{i}"] = SourcePolicy(f"src-ai{i}", "vertical", 48, 3.0, "standard")
        policies[f"src-t{i}"] = SourcePolicy(f"src-t{i}", "vertical", 48, 3.0, "standard")
        policies[f"src-g{i}"] = SourcePolicy(f"src-g{i}", "vertical", 48, 3.0, "standard")

    result = select_digest(items, policies, now)
    assert result.category_counts["ai"] >= 3
    assert result.category_counts["tool"] >= 2
    assert result.category_counts["game"] >= 2
    assert len(result.selected) <= 10


def test_top_n_limit():
    """最多选 10 条。"""
    from app.pipeline.selection import select_digest

    now = _NOW
    today = now.strftime("%Y-%m-%d")
    items = [
        _make_item(title=f"Item-{i}", url=f"https://x{i}.test",
                   source=f"src-{i}", category="ai",
                   published_at=f"{today}T08:00:00+08:00")
        for i in range(30)
    ]
    policies = {
        f"src-{i}": SourcePolicy(f"src-{i}", "vertical", 48, 3.0, "standard")
        for i in range(30)
    }
    result = select_digest(items, policies, now)
    assert len(result.selected) <= 10


def test_deterministic_output():
    """相同输入两次调用产生相同输出（确定性）。"""
    from app.pipeline.selection import select_digest

    now = _NOW
    today = now.strftime("%Y-%m-%d")
    items = [
        _make_item(title="A", url="https://later.test",
                   source="src-a", category="ai",
                   published_at=f"{today}T09:00:00+08:00",
                   canonical_key="later"),
        _make_item(title="B", url="https://earlier.test",
                   source="src-b", category="ai",
                   published_at=f"{today}T08:00:00+08:00",
                   canonical_key="earlier"),
    ]
    policies = {
        "src-a": SourcePolicy("src-a", "vertical", 48, 3.0, "standard"),
        "src-b": SourcePolicy("src-b", "vertical", 48, 3.0, "standard"),
    }
    r1 = select_digest(items, policies, now)
    r2 = select_digest(items, policies, now)
    assert len(r1.selected) == len(r2.selected)
    assert [e.canonical_key for e in r1.evidence] == [e.canonical_key for e in r2.evidence]


def test_selection_result_has_evidence():
    """SelectionResult 包含 evidence 和 category_counts。"""
    from app.pipeline.selection import select_digest

    now = _NOW
    items, policies = build_selection_fixture(now)
    result = select_digest(items, policies, now)

    assert len(result.evidence) > 0
    assert len(result.evidence) == len(result.selected)
    for e in result.evidence:
        assert e.final_score > 0
        assert e.canonical_key
        assert isinstance(e.diversity_penalty, float)
        assert isinstance(e.selection_score, float)
        assert e.phase in {"today_guarantee", "historical_backfill", "today_competition"}
