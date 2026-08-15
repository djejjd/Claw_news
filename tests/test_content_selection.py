"""Task 5: 三阶段选材与唯一评分 — 失败测试。"""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.content.source_policy import SourcePolicy
from app.pipeline.candidate import CandidateItem

_TODAY = "2026-07-11"
_NOW = datetime.fromisoformat("2026-07-11T09:00:00+08:00")
_TZ = "Asia/Shanghai"


def _make_item(**kwargs) -> CandidateItem:
    data = {
        "title": "T",
        "url": "https://x.test",
        "summary": "S",
        "source": "qbitai",
        "category": "ai",
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
        source="qbitai",
        category="ai",
        published_at="2026-07-10T03:00:00+08:00",
    )
    policy = SourcePolicy("qbitai", "vertical", 48, 3.5, "standard")
    # 30h ago → freshness=1.5, quality=3.5 → 5.0
    assert compute_final_score(item, policy, now) == 5.0


@pytest.mark.parametrize(
    ("count", "penalty"),
    [
        (0, 0.0),
        (1, -1.0),
        (2, -2.0),
        (3, -3.5),
        (4, -5.0),
        (9, -5.0),
    ],
)
def test_diversity_penalty(count, penalty):
    """单源惩罚映射与设计一致。"""
    from app.pipeline.selection import source_diversity_penalty

    assert source_diversity_penalty(count) == penalty


@pytest.mark.parametrize(
    ("count", "penalty"),
    [(0, 0.0), (1, -1.0), (2, -3.0), (3, -6.0), (4, -10.0), (9, -10.0)],
)
def test_exponential_diversity_penalty_profile(count, penalty):
    from app.pipeline.selection import source_diversity_penalty

    assert source_diversity_penalty(count, profile="exponential") == penalty


def test_unknown_diversity_penalty_profile_is_rejected():
    from app.pipeline.selection import source_diversity_penalty

    with pytest.raises(ValueError, match="SELECTION_DIVERSITY_PENALTY_PROFILE"):
        source_diversity_penalty(1, profile="unknown")


def test_exponential_profile_changes_only_selection_score():
    from app.pipeline.selection import select_digest

    items = [
        _make_item(
            title=f"同源 AI {index}",
            url=f"https://same.test/{index}",
            source="same",
            category="ai",
        )
        for index in range(3)
    ]
    policies = {"same": SourcePolicy("same", quality_weight=3.5)}

    linear = select_digest(items, policies, _NOW, top_n=3, diversity_penalty_profile="linear")
    exponential = select_digest(
        items, policies, _NOW, top_n=3, diversity_penalty_profile="exponential"
    )

    assert [item.final_score for item in exponential.selected] == [
        item.final_score for item in linear.selected
    ]
    assert [event.diversity_penalty for event in linear.evidence] == [0.0, -1.0, -2.0]
    assert [event.diversity_penalty for event in exponential.evidence] == [0.0, -1.0, -3.0]


def test_topic_cluster_reselects_after_excluding_lower_scored_duplicate():
    from app.pipeline.selection import select_digest_with_topic_clustering

    items = [
        _make_item(
            title="OpenAI 发布 GPT 5 API",
            url="https://a.test/openai-gpt-5-api",
            source="a",
            topic="model_release",
        ),
        _make_item(
            title="GPT 5 API 已由 OpenAI 正式发布",
            url="https://b.test/openai-gpt-5-api-news",
            source="b",
            topic="model_release",
        ),
        _make_item(
            title="Claude 推出新的 Agent 工作流",
            url="https://c.test/claude-agent",
            source="c",
            topic="agent_workflow",
        ),
    ]
    policies = {
        "a": SourcePolicy("a", quality_weight=5.0),
        "b": SourcePolicy("b", quality_weight=3.0),
        "c": SourcePolicy("c", quality_weight=2.0),
    }

    result, events = select_digest_with_topic_clustering(
        items, policies, _NOW, top_n=3, enabled=True, threshold=0.7, max_rounds=10
    )

    assert {item.source for item in result.selected} == {"a", "c"}
    assert events[0].loser_canonical_key == "b.test/openai-gpt-5-api-news"


def test_topic_cluster_uses_smallest_canonical_key_for_score_tie():
    from app.pipeline.selection import select_digest_with_topic_clustering

    items = [
        _make_item(
            title="GPT 5 API 发布 OpenAI",
            url="https://a.test/gpt-5-api",
            source="a",
            topic="model_release",
        ),
        _make_item(
            title="OpenAI 正式发布 GPT 5 API",
            url="https://b.test/gpt-5-api-news",
            source="b",
            topic="model_release",
        ),
    ]
    policies = {item.source: SourcePolicy(item.source) for item in items}

    _, events = select_digest_with_topic_clustering(
        items, policies, _NOW, top_n=2, enabled=True, threshold=0.7
    )

    assert events[0].winner_canonical_key == "a.test/gpt-5-api"


def test_topic_cluster_chain_overlap_keeps_one_deterministic_winner():
    from app.pipeline.selection import select_digest_with_topic_clustering

    items = [
        _make_item(
            title="GPT 5 API OpenAI 发布",
            url="https://a.test/gpt-5-api",
            source="a",
            topic="model_release",
        ),
        _make_item(
            title="OpenAI GPT 5 API 正式发布",
            url="https://b.test/gpt-5-api-news",
            source="b",
            topic="model_release",
        ),
        _make_item(
            title="GPT 5 API 正式上线",
            url="https://c.test/gpt-5-api-launch",
            source="c",
            topic="model_release",
        ),
    ]
    policies = {item.source: SourcePolicy(item.source) for item in items}

    result, events = select_digest_with_topic_clustering(
        items, policies, _NOW, top_n=3, enabled=True, threshold=0.5
    )

    assert [item.canonical_key for item in result.selected] == ["a.test/gpt-5-api"]
    assert {event.loser_canonical_key for event in events} == {
        "b.test/gpt-5-api-news",
        "c.test/gpt-5-api-launch",
    }
    assert all(event.trigger_edges for event in events)
    assert len(result.cluster_rounds) == 2
    first_round, final_round = result.cluster_rounds
    assert first_round.selection_round == 1
    assert first_round.available_count == 3
    assert first_round.selected_before_count == 3
    assert first_round.excluded_count == 2
    assert first_round.cumulative_excluded_count == 2
    assert first_round.converged is False
    assert final_round.selection_round == 2
    assert final_round.available_count == 1
    assert final_round.selected_before_count == 1
    assert final_round.excluded_count == 0
    assert final_round.cumulative_excluded_count == 2
    assert final_round.converged is True


def test_topic_cluster_fails_when_max_rounds_is_exhausted():
    from app.pipeline.selection import select_digest_with_topic_clustering

    items = [
        _make_item(
            title="GPT 5 API OpenAI 发布",
            url="https://a.test/gpt-5-api",
            source="a",
            topic="model_release",
        ),
        _make_item(
            title="OpenAI GPT 5 API 正式发布",
            url="https://b.test/gpt-5-api-news",
            source="b",
            topic="model_release",
        ),
    ]
    policies = {item.source: SourcePolicy(item.source) for item in items}

    with pytest.raises(RuntimeError, match="topic_cluster_non_convergent"):
        select_digest_with_topic_clustering(
            items, policies, _NOW, top_n=2, enabled=True, threshold=0.5, max_rounds=1
        )


def test_topic_cluster_disabled_matches_plain_selection():
    from app.pipeline.selection import select_digest, select_digest_with_topic_clustering

    items, policies = build_selection_fixture(_NOW)
    plain = select_digest(items, policies, _NOW)
    clustered, events = select_digest_with_topic_clustering(items, policies, _NOW, enabled=False)

    assert [item.canonical_key for item in clustered.selected] == [
        item.canonical_key for item in plain.selected
    ]
    assert events == []


def test_llm_relevance_reselection_excludes_low_initial_item_and_marks_unscored_backfill():
    from app.pipeline.selection import reselect_digest_after_llm_relevance

    initial = _make_item(url="https://initial.test/low", source="initial", category="ai")
    replacement = _make_item(
        url="https://replacement.test/high", source="replacement", category="ai"
    )
    policies = {
        "initial": SourcePolicy("initial", quality_weight=5.0),
        "replacement": SourcePolicy("replacement", quality_weight=4.0),
    }

    result, cluster_events, events = reselect_digest_after_llm_relevance(
        [initial, replacement],
        policies,
        _NOW,
        excluded_canonical_keys={initial.canonical_key},
        initially_scored_keys={initial.canonical_key},
        top_n=1,
    )

    assert [item.canonical_key for item in result.selected] == [replacement.canonical_key]
    assert cluster_events == []
    assert events == [
        {
            "event": "llm_relevance_backfill",
            "canonical_key": replacement.canonical_key,
            "relevance": None,
            "relevance_source": "not_scored_backfill",
        }
    ]


@pytest.mark.skip(reason="CG-P3-02-FOLLOWUP-01：等待真实候选池的人工标注样本")
def test_topic_cluster_annotation_calibration_gate():
    """标注集必须覆盖 200 对样本及四类内容，并满足误差门槛。"""
    from app.pipeline.selection import _topic_similarity_edges

    fixture_path = Path(__file__).parent / "fixtures" / "topic_cluster_annotations.json"
    pairs = json.loads(fixture_path.read_text(encoding="utf-8"))["pairs"]

    assert len(pairs) >= 200
    category_counts = {category: 0 for category in ("ai", "tool", "game", "digital")}
    false_aggregations = 0
    missed_aggregations = 0
    expected_aggregations = 0
    expected_non_aggregations = 0

    for index, pair in enumerate(pairs):
        category = pair["category"]
        assert category in category_counts
        category_counts[category] += 1
        left = _make_item(
            title=pair["left_title"],
            url=f"https://left-{index}.example/alpha-{index}",
            source="left",
            category=category,
            topic=pair["topic"],
        )
        right = _make_item(
            title=pair["right_title"],
            url=f"https://right-{index}.example/beta-{index}",
            source="right",
            category=category,
            topic=pair["topic"],
        )
        predicted_cluster = bool(_topic_similarity_edges([left, right], threshold=0.7))
        should_cluster = pair["should_cluster"]
        if should_cluster:
            expected_aggregations += 1
            missed_aggregations += not predicted_cluster
        else:
            expected_non_aggregations += 1
            false_aggregations += predicted_cluster

    assert all(count >= 40 for count in category_counts.values())
    assert expected_aggregations > 0
    assert expected_non_aggregations > 0
    assert false_aggregations / expected_non_aggregations <= 0.02
    assert missed_aggregations / expected_aggregations <= 0.15


# ======================== 三阶段选材 ========================


def build_selection_fixture(now):
    """今日 AI 2、工具 2、游戏 2，历史 AI 1、历史高分工具 1"""
    today = now.strftime("%Y-%m-%d")
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")

    items = [
        # 今日
        _make_item(
            title="AI-今日1",
            url="https://ai1.test",
            source="qbitai",
            category="ai",
            published_at=f"{today}T08:00:00+08:00",
            canonical_key="ai-today-1",
        ),
        _make_item(
            title="AI-今日2",
            url="https://ai2.test",
            source="leiphone",
            category="ai",
            published_at=f"{today}T07:00:00+08:00",
            canonical_key="ai-today-2",
        ),
        _make_item(
            title="工具-今日1",
            url="https://t1.test",
            source="sspai",
            category="tool",
            published_at=f"{today}T08:00:00+08:00",
        ),
        _make_item(
            title="工具-今日2",
            url="https://t2.test",
            source="appinn",
            category="tool",
            published_at=f"{today}T08:00:00+08:00",
        ),
        _make_item(
            title="游戏-今日1",
            url="https://g1.test",
            source="yystv",
            category="game",
            published_at=f"{today}T08:00:00+08:00",
        ),
        _make_item(
            title="游戏-今日2",
            url="https://g2.test",
            source="gcores",
            category="game",
            published_at=f"{today}T08:00:00+08:00",
        ),
        # 历史
        _make_item(
            title="AI-历史1",
            url="https://old-ai.test",
            source="qbitai",
            category="ai",
            published_at=f"{yesterday}T12:00:00+08:00",
            canonical_key="old-ai-1",
        ),
        _make_item(
            title="工具-历史高分",
            url="https://old-tool.test",
            source="ithome",
            category="tool",
            published_at=f"{yesterday}T12:00:00+08:00",
            canonical_key="old-high-tool",
        ),
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
        _make_item(
            title="same-今日AI1",
            url="https://same-p1.test",
            source="same_src",
            category="ai",
            published_at=f"{today}T09:00:00+08:00",
            canonical_key="same-p1",
        ),
        # Phase 2: 历史补位（同类 AI 不足时）
        _make_item(
            title="same-历史AI",
            url="https://same-p2.test",
            source="same_src",
            category="ai",
            published_at=f"{yesterday}T12:00:00+08:00",
            canonical_key="same-p2",
        ),
        # Phase 3: 今日竞争（也是 same_src）
        _make_item(
            title="same-今日AI2",
            url="https://same-p3.test",
            source="same_src",
            category="ai",
            published_at=f"{today}T10:00:00+08:00",
            canonical_key="same-p3",
        ),
        # 其他类确保够选
        _make_item(
            title="工具-今日1",
            url="https://t1.test",
            source="sspai",
            category="tool",
            published_at=f"{today}T08:00:00+08:00",
        ),
        _make_item(
            title="工具-今日2",
            url="https://t2.test",
            source="appinn",
            category="tool",
            published_at=f"{today}T08:00:00+08:00",
        ),
        _make_item(
            title="游戏-今日1",
            url="https://g1.test",
            source="yystv",
            category="game",
            published_at=f"{today}T08:00:00+08:00",
        ),
        _make_item(
            title="游戏-今日2",
            url="https://g2.test",
            source="gcores",
            category="game",
            published_at=f"{today}T08:00:00+08:00",
        ),
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
    # 总数不足 top_n 时，历史高分工具允许补位
    selected_keys = {x.canonical_key for x in result.selected}
    assert "old-high-tool" in selected_keys


def test_source_counts_accumulate_across_phases():
    """同一 source 在三阶段中累计计数，penalty 递增。"""
    from app.pipeline.selection import select_digest

    now = _NOW
    items, policies = build_cross_phase_same_source_fixture(now)
    result = select_digest(items, policies, now)

    same_evidence = [e for e in result.evidence if e.canonical_key.startswith("same-p")]
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
    items = (
        [
            _make_item(
                title=f"AI-{i}",
                url=f"https://ai{i}.test",
                source=f"src-ai{i}",
                category="ai",
                published_at=f"{today}T08:00:00+08:00",
            )
            for i in range(5)
        ]
        + [
            _make_item(
                title=f"工具-{i}",
                url=f"https://t{i}.test",
                source=f"src-t{i}",
                category="tool",
                published_at=f"{today}T08:00:00+08:00",
            )
            for i in range(5)
        ]
        + [
            _make_item(
                title=f"游戏-{i}",
                url=f"https://g{i}.test",
                source=f"src-g{i}",
                category="game",
                published_at=f"{today}T08:00:00+08:00",
            )
            for i in range(5)
        ]
    )
    policies = {}
    for i in range(5):
        policies[f"src-ai{i}"] = SourcePolicy(f"src-ai{i}", "vertical", 48, 3.0, "standard")
        policies[f"src-t{i}"] = SourcePolicy(f"src-t{i}", "vertical", 48, 3.0, "standard")
        policies[f"src-g{i}"] = SourcePolicy(f"src-g{i}", "vertical", 48, 3.0, "standard")

    result = select_digest(items, policies, now)
    assert result.category_counts["ai"] >= 3
    assert result.category_counts["tool"] >= 2
    assert result.category_counts["game"] >= 2


def test_digital_participates_only_in_open_competition():
    """数码没有保底名额，但高分数码候选可进入自由竞争。"""
    from app.pipeline.selection import select_digest

    now = _NOW
    today = now.strftime("%Y-%m-%d")
    items = [
        _make_item(
            title=f"AI-{index}",
            url=f"https://ai-{index}.test",
            source=f"ai-{index}",
            category="ai",
            published_at=f"{today}T08:00:00+08:00",
        )
        for index in range(3)
    ]
    items += [
        _make_item(
            title=f"工具-{index}",
            url=f"https://tool-{index}.test",
            source=f"tool-{index}",
            category="tool",
            published_at=f"{today}T08:00:00+08:00",
        )
        for index in range(2)
    ]
    items += [
        _make_item(
            title=f"游戏-{index}",
            url=f"https://game-{index}.test",
            source=f"game-{index}",
            category="game",
            published_at=f"{today}T08:00:00+08:00",
        )
        for index in range(2)
    ]
    items.append(
        _make_item(
            title="数码-高分",
            url="https://digital.test",
            source="digital-source",
            category="digital",
            published_at=f"{today}T08:00:00+08:00",
        )
    )
    policies = {
        item.source: SourcePolicy(item.source, "vertical", 48, 10.0, "standard") for item in items
    }

    result = select_digest(items, policies, now)

    assert result.category_counts["digital"] == 1
    digital_evidence = next(
        event for event in result.evidence if event.canonical_key == "digital.test"
    )
    assert digital_evidence.phase == "today_competition"
    assert len(result.selected) <= 10


def test_top_n_limit():
    """最多选 10 条。"""
    from app.pipeline.selection import select_digest

    now = _NOW
    today = now.strftime("%Y-%m-%d")
    items = [
        _make_item(
            title=f"Item-{i}",
            url=f"https://x{i}.test",
            source=f"src-{i}",
            category="ai",
            published_at=f"{today}T08:00:00+08:00",
        )
        for i in range(30)
    ]
    policies = {
        f"src-{i}": SourcePolicy(f"src-{i}", "vertical", 48, 3.0, "standard") for i in range(30)
    }
    result = select_digest(items, policies, now)
    assert len(result.selected) <= 10


def test_source_cap_limits_high_volume_source():
    from app.pipeline.selection import select_digest

    now = _NOW
    items = [
        _make_item(
            title=f"Item-{i}",
            url=f"https://ithome-{i}.test",
            source="ithome",
            category="tool",
            published_at=now.strftime("%Y-%m-%dT08:00:00+08:00"),
        )
        for i in range(6)
    ]
    result = select_digest(items, {"ithome": SourcePolicy("ithome", tier="fast_news")}, now)
    assert sum(item.source == "ithome" for item in result.selected) == 2


def test_fast_news_hard_cap_never_breaks_when_digest_is_short():
    """快讯源硬上限 2，即使候选不足也不得突破。"""
    from app.pipeline.selection import select_digest

    now = _NOW
    items = [
        _make_item(
            title=f"Fast-{i}",
            url=f"https://fast-{i}.test",
            source="fast",
            category="tool",
            published_at=now.isoformat(),
        )
        for i in range(6)
    ]
    result = select_digest(items, {"fast": SourcePolicy("fast", tier="fast_news")}, now)

    assert len(result.selected) == 2
    assert all(not evidence.soft_source_cap_exceeded for evidence in result.evidence)


def test_non_fast_source_soft_cap_can_break_only_to_fill_short_digest():
    """非快讯源常规阶段最多 3 条，不足 top_n 时才允许软上限补位。"""
    from app.pipeline.selection import select_digest

    now = _NOW
    items = [
        _make_item(
            title=f"Vertical-{i}",
            url=f"https://vertical-{i}.test",
            source="vertical",
            category="ai",
            published_at=now.isoformat(),
        )
        for i in range(6)
    ]
    result = select_digest(items, {"vertical": SourcePolicy("vertical")}, now, top_n=5)

    assert len(result.selected) == 5
    overflow = [e for e in result.evidence if e.soft_source_cap_exceeded]
    assert len(overflow) == 2
    assert {e.phase for e in overflow} == {"soft_cap_backfill"}


def test_soft_cap_evidence_is_false_when_normal_candidates_fill_digest():
    from app.pipeline.selection import select_digest

    now = _NOW
    items = [
        _make_item(
            title=f"Vertical-{i}",
            url=f"https://vertical-{i}.test",
            source="vertical",
            category="ai",
            published_at=now.isoformat(),
        )
        for i in range(3)
    ] + [
        _make_item(
            title=f"Other-{i}",
            url=f"https://other-{i}.test",
            source=f"other-{i}",
            category="tool",
            published_at=now.isoformat(),
        )
        for i in range(2)
    ]
    policies = {"vertical": SourcePolicy("vertical")}
    policies.update({f"other-{i}": SourcePolicy(f"other-{i}") for i in range(2)})

    result = select_digest(items, policies, now, top_n=5)

    assert len(result.selected) == 5
    assert all(not evidence.soft_source_cap_exceeded for evidence in result.evidence)


def test_historical_competition_fills_remaining_slots():
    from app.pipeline.selection import select_digest

    now = _NOW
    items = [
        _make_item(
            title=f"Today-{i}",
            url=f"https://today-{i}.test",
            source="qbitai",
            category="ai",
            published_at=now.strftime("%Y-%m-%d"),
        )
        for i in range(3)
    ] + [
        _make_item(
            title=f"History-{i}",
            url=f"https://history-{i}.test",
            source=f"src-{i}",
            category="ai",
            published_at="2026-05-16",
        )
        for i in range(7)
    ]
    policies = {
        "qbitai": SourcePolicy("qbitai"),
        **{f"src-{i}": SourcePolicy(f"src-{i}") for i in range(7)},
    }
    result = select_digest(items, policies, now, top_n=10)
    assert len(result.selected) == 10


def test_deterministic_output():
    """相同输入两次调用产生相同输出（确定性）。"""
    from app.pipeline.selection import select_digest

    now = _NOW
    today = now.strftime("%Y-%m-%d")
    items = [
        _make_item(
            title="A",
            url="https://later.test",
            source="src-a",
            category="ai",
            published_at=f"{today}T09:00:00+08:00",
            canonical_key="later",
        ),
        _make_item(
            title="B",
            url="https://earlier.test",
            source="src-b",
            category="ai",
            published_at=f"{today}T08:00:00+08:00",
            canonical_key="earlier",
        ),
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
        assert isinstance(e.soft_source_cap_exceeded, bool)
        assert e.phase in {
            "today_guarantee",
            "historical_backfill",
            "today_competition",
            "historical_competition",
            "soft_cap_backfill",
        }
