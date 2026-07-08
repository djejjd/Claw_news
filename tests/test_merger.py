from datetime import date as _date
from datetime import timedelta

from aggregator.merger import (
    DEFAULT_AI_SOURCE_WEIGHT,
    DEFAULT_OTHER_SOURCE_WEIGHT,
    DEFAULT_TOPIC_WEIGHT,
    KEYWORD_BONUS,
    SOURCE_WEIGHTS,
    TOPIC_WEIGHTS,
    Merger,
    compute_final_score,
    compute_source_score,
    position_score,
)
from app.pipeline.candidate import CandidateItem
from collectors.base import HotItem, time_modifier

# =============================================================================
# Existing tests (unchanged)
# =============================================================================


class TestPositionScore:
    def test_position_score_first(self):
        assert position_score(1) == 10.0

    def test_position_score_last(self):
        assert position_score(10) == 5.5

    def test_position_score_decreasing(self):
        assert position_score(1) > position_score(5) > position_score(10)

    def test_position_score_clamp(self):
        assert position_score(0) == 10.0
        assert position_score(100) == 5.5


class TestComputeSourceScore:
    def test_hf_keeps_original(self):
        item = HotItem("t", "", "", "huggingface", "ai", 9.0)
        assert compute_source_score(item, position=1) == 9.0

    def test_taptap_keeps_original(self):
        item = HotItem("t", "", "", "taptap", "game", 8.0)
        assert compute_source_score(item, position=1) == 8.0

    def test_rss_with_keyword_and_today(self):
        today = _date.today().isoformat()
        item = HotItem("t", "", "", "qbitai", "ai", 5.0, keyword_hit=True, pub_date=today)
        score = compute_source_score(item, position=1, period="morning")
        # position_score(1)=10.0 + keyword_bonus=1.0 + time_modifier=0
        assert score == 11.0

    def test_rss_no_keyword_old(self):
        item = HotItem("t", "", "", "yystv", "game", 5.0, keyword_hit=False, pub_date="2026-05-10")
        score = compute_source_score(item, position=5, period="morning")
        # position_score(5)=8.0 + keyword_bonus=0 + time_modifier(old)=-2.0
        assert score == 6.0


class TestMerger:
    def test_groups_by_category(self, sample_items_v2):
        merger = Merger(top_n=5)
        result = merger.merge(sample_items_v2, period="morning")
        assert set(result.keys()) == {"ai", "game", "tool"}

    def test_device_alias_normalizes_into_tool_bucket(self):
        merger = Merger(top_n=5)
        items = [
            HotItem("Tool 1", "https://tool.example.com/1", "s", "sspai", "tool", 5.0),
            HotItem("Tool 2", "https://tool.example.com/2", "s", "ithome", "device", 5.0),
        ]

        result = merger.merge(items, period="morning")

        assert [item.url for item in result["tool"]] == [
            "https://tool.example.com/1",
            "https://tool.example.com/2",
        ]

    def test_sorts_desc(self, sample_items_v2):
        merger = Merger(top_n=5)
        result = merger.merge(sample_items_v2, period="morning")
        for items in result.values():
            if items:
                scores = [item.source_score for item in items]
                assert scores == sorted(scores, reverse=True)

    def test_top_n_limit(self, sample_items_v2):
        merger = Merger(top_n=5)
        result = merger.merge(sample_items_v2, period="morning")
        for items in result.values():
            assert len(items) <= 5

    def test_empty_input(self):
        merger = Merger(top_n=5)
        result = merger.merge([], period="morning")
        assert result == {"ai": [], "game": [], "tool": []}

    def test_each_source_has_at_least_one(self, sample_items_v2):
        """每源至少 1 条出现在结果中（V2 关键词保底规则）"""
        merger = Merger(top_n=5)
        result = merger.merge(sample_items_v2, period="morning")

        for category, items in result.items():
            if not items:
                continue
            # Count sources in input
            input_sources = {item.source for item in sample_items_v2 if item.category == category}
            # Each input source should appear at least once in result
            for src in input_sources:
                # At least 1 item should be from this source
                assert any(item.source == src for item in items), (
                    f"Category {category}: source {src} missing from result"
                )

    def test_time_modifier_import(self):
        """time_modifier 可正常导入"""
        assert callable(time_modifier)


# =============================================================================
# Phase 4: New scoring tests
# =============================================================================

_TODAY = _date.today().isoformat()
_YESTERDAY = (_date.today() - timedelta(days=1)).isoformat()
_OLD_DATE = (_date.today() - timedelta(days=7)).isoformat()


# ---- helpers ----


def _make_candidate(
    title="Test Item",
    url="https://example.com/1",
    source="qbitai",
    topic="agent_workflow",
    source_weight=None,
    topic_weight=None,
    keyword_bonus=None,
    keyword_hit=False,
    pub_date=None,
    published_at=None,
    category="ai",
    summary="A test item",
    final_score=None,
):
    """Factory for CandidateItem with Phase 4 scoring fields."""
    if pub_date is None:
        pub_date = _TODAY
    if published_at is None:
        published_at = pub_date
    return CandidateItem(
        title=title,
        url=url,
        summary=summary,
        source=source,
        category=category,
        published_at=published_at or pub_date,
        topic=topic,
        source_weight=source_weight,
        topic_weight=topic_weight,
        keyword_bonus=keyword_bonus,
        final_score=final_score,
    )


def _make_hotitem(
    title="Test Item",
    url="https://example.com/1",
    source="qbitai",
    keyword_hit=False,
    pub_date=None,
    category="ai",
    source_score=5.0,
):
    """Factory for HotItem."""
    if pub_date is None:
        pub_date = _TODAY
    return HotItem(
        title=title,
        url=url,
        summary="A test item",
        source=source,
        category=category,
        source_score=source_score,
        keyword_hit=keyword_hit,
        pub_date=pub_date,
    )


class TestComputeFinalScore:
    """compute_final_score 单元测试"""

    def test_basic_calculation(self):
        """source_weight + topic_weight + keyword_bonus + time_modifier"""
        item = _make_candidate(
            source="qbitai",
            source_weight=3.0,
            topic="agent_workflow",
            topic_weight=2.5,
            keyword_bonus=0.5,
        )
        score = compute_final_score(item)
        # sw=3.0 + tw=2.5 + kb=0.5 + tm(today)=0 = 6.0
        assert score == 6.0

    def test_no_keyword_bonus(self):
        """关键词未命中时不加分"""
        item = _make_candidate(
            source="qbitai",
            source_weight=3.0,
            topic="agent_workflow",
            topic_weight=2.5,
            keyword_bonus=0.0,
        )
        score = compute_final_score(item)
        assert score == 5.5  # 3.0+2.5+0+0

    def test_keyword_hit_true_fallback(self):
        """keyword_bonus 为 None 但 keyword_hit=True 时加分"""
        item = _make_candidate(
            source="qbitai",
            source_weight=3.0,
            topic="agent_workflow",
            topic_weight=2.5,
            keyword_bonus=None,
        )
        # CandidateItem has no keyword_hit, so getattr returns False → no bonus
        score_no_kw = compute_final_score(item)
        assert score_no_kw == 5.5  # 3.0+2.5+0+0

        # HotItem with keyword_hit=True
        hot = _make_hotitem(keyword_hit=True)
        score_hot = compute_final_score(hot)
        # source_weight via SOURCE_WEIGHTS (qbitai=3.0) + topic_weight via
        # TOPIC_WEIGHTS (hot has no topic → default=1.0) + kb=0.5 + tm=0 = 4.5
        assert score_hot == 4.5

    def test_unknown_source_default_weight(self):
        """未知 source 使用 DEFAULT_AI_SOURCE_WEIGHT"""
        item = _make_candidate(
            source="unknown_source_xyz",
            source_weight=None,
            topic="application_case",
            topic_weight=1.0,
            keyword_bonus=0.0,
        )
        score = compute_final_score(item)
        # sw=DEFAULT_AI_SOURCE_WEIGHT=3.0 + tw=1.0 + kb=0 + tm=0 = 4.0
        assert score == 4.0

    def test_unknown_topic_default_weight(self):
        """未知 topic 使用 DEFAULT_TOPIC_WEIGHT"""
        item = _make_candidate(
            source="qbitai",
            source_weight=3.0,
            topic="unknown_topic_xyz",
            topic_weight=None,
            keyword_bonus=0.0,
        )
        score = compute_final_score(item)
        # sw=3.0 + tw=DEFAULT_TOPIC_WEIGHT=1.0 + kb=0 + tm=0 = 4.0
        assert score == 4.0

    def test_old_pub_date_time_modifier(self):
        """较旧的 pub_date 应用 time_modifier 衰减"""
        item = _make_candidate(
            source="qbitai",
            source_weight=3.0,
            topic="application_case",
            topic_weight=1.0,
            keyword_bonus=0.0,
            pub_date=_OLD_DATE,  # 7 days old → time_modifier=-2.0
        )
        score = compute_final_score(item)
        # sw=3.0 + tw=1.0 + kb=0 + tm=-2.0 = 2.0
        assert score == 2.0

    def test_published_at_fallback(self):
        """pub_date 为空时回退到 published_at"""
        item = CandidateItem(
            title="Test",
            url="https://x.com/1",
            summary="x",
            source="qbitai",
            category="ai",
            published_at=_TODAY,
            topic="application_case",
            source_weight=3.0,
            topic_weight=1.0,
            keyword_bonus=0.0,
        )
        score = compute_final_score(item)
        # sw=3.0 + tw=1.0 + kb=0 + tm=0 = 4.0
        assert score == 4.0

    def test_huggingface_source_weight(self):
        """HF 来源权重 = 4.0"""
        item = _make_candidate(
            source="huggingface",
            source_weight=None,
            topic="model_release",
            topic_weight=3.0,
            keyword_bonus=0.5,
        )
        score = compute_final_score(item)
        # SOURCE_WEIGHTS[huggingface]=4.0 + tw=3.0 + kb=0.5 + tm=0 = 7.5
        assert score == 7.5

    def test_topic_weights_mapping(self):
        """验证 6 个主题桶的权重"""
        expected = {
            "model_release": 3.0,
            "agent_workflow": 2.5,
            "developer_tooling": 2.0,
            "research_benchmark": 2.0,
            "infrastructure": 1.5,
            "application_case": 1.0,
        }
        for topic, weight in expected.items():
            item = _make_candidate(
                source="qbitai",
                source_weight=0.0,
                topic=topic,
                topic_weight=None,
                keyword_bonus=0.0,
            )
            score = compute_final_score(item)
            # sw=0 + topic_weight + kb=0 + tm=0 = topic_weight
            assert score == weight, f"topic={topic}: expected {weight}, got {score}"

    def test_source_weights_mapping(self):
        """验证来源权重：huggingface=4.0, qbitai=3.0, 其他AI默认=3.0"""
        # huggingface
        item_hf = _make_candidate(
            source="huggingface",
            source_weight=None,
            topic="application_case",
            topic_weight=0.0,
            keyword_bonus=0.0,
        )
        assert compute_final_score(item_hf) == 4.0  # sw=4.0 + tw=0 + kb=0 + tm=0

        # qbitai
        item_qb = _make_candidate(
            source="qbitai",
            source_weight=None,
            topic="application_case",
            topic_weight=0.0,
            keyword_bonus=0.0,
        )
        assert compute_final_score(item_qb) == 3.0  # sw=3.0 + tw=0 + kb=0 + tm=0

        # unknown AI source
        item_unknown = _make_candidate(
            source="some_ai_blog",
            source_weight=None,
            topic="application_case",
            topic_weight=0.0,
            keyword_bonus=0.0,
        )
        assert compute_final_score(item_unknown) == 3.0  # DEFAULT_AI_SOURCE_WEIGHT=3.0


class TestMergerNewScoring:
    """Merger.merge(use_new_scoring=True) 测试"""

    def test_returns_sorted_list(self):
        """返回按 final_score 降序排列的 CandidateItem 列表"""
        merger = Merger(top_n=3)
        items = [
            _make_candidate(
                title="Low",
                url="https://a.com/low",
                source_weight=1.0,
                topic_weight=1.0,
                keyword_bonus=0.0,
            ),
            _make_candidate(
                title="High",
                url="https://a.com/high",
                source_weight=3.0,
                topic_weight=3.0,
                keyword_bonus=0.5,
            ),
            _make_candidate(
                title="Mid",
                url="https://a.com/mid",
                source_weight=2.0,
                topic_weight=2.0,
                keyword_bonus=0.0,
            ),
        ]
        result = merger.merge(items, use_new_scoring=True)
        assert isinstance(result, list)
        assert len(result) == 3
        scores = [item.final_score for item in result]
        assert scores == sorted(scores, reverse=True)

    def test_respects_top_n(self):
        """TopN 限制生效"""
        merger = Merger(top_n=2)
        items = [
            _make_candidate(
                title=f"Item {i}",
                url=f"https://a.com/{i}",
                source_weight=float(i),
                topic_weight=1.0,
                keyword_bonus=0.0,
            )
            for i in range(5)
        ]
        result = merger.merge(items, use_new_scoring=True)
        assert len(result) == 2

    def test_no_per_source_guarantee(self):
        """新评分不做每源保底：2 条同源高分项可同时占据 TopN"""
        merger = Merger(top_n=2)
        items = [
            _make_candidate(
                title="SameSource-1",
                url="https://srcA.com/1",
                source="huggingface",
                source_weight=None,
                topic="model_release",
                topic_weight=None,
                keyword_bonus=0.5,
            ),
            _make_candidate(
                title="SameSource-2",
                url="https://srcA.com/2",
                source="huggingface",
                source_weight=None,
                topic="model_release",
                topic_weight=None,
                keyword_bonus=0.5,
            ),
            _make_candidate(
                title="OtherSource",
                url="https://srcB.com/1",
                source="ithome",
                source_weight=None,
                topic="application_case",
                topic_weight=None,
                keyword_bonus=0.0,
            ),
        ]
        result = merger.merge(items, use_new_scoring=True)
        # Both top items can be from huggingface (same source)
        sources = [item.source for item in result]
        # Both should be "huggingface" since they have higher scores
        assert sources.count("huggingface") == 2

    def test_empty_input(self):
        """空输入返回空列表"""
        merger = Merger(top_n=5)
        result = merger.merge([], use_new_scoring=True)
        assert result == []

    def test_dedup_keeps_higher_score(self):
        """去重保留 final_score 更高的项"""
        merger = Merger(top_n=5)
        items = [
            _make_candidate(
                title="Low score dup",
                url="https://dup.com/1",
                source_weight=1.0,
                topic_weight=1.0,
                keyword_bonus=0.0,
            ),
            _make_candidate(
                title="High score original",
                url="https://dup.com/1",
                source_weight=3.0,
                topic_weight=3.0,
                keyword_bonus=0.5,
            ),
        ]
        result = merger.merge(items, use_new_scoring=True)
        urls = [item.url for item in result]
        assert urls.count("https://dup.com/1") == 1
        kept = next(item for item in result if item.url == "https://dup.com/1")
        assert kept.title == "High score original"

    def test_returns_candidate_items(self):
        """返回的列表元素为 CandidateItem（或具有 final_score 属性）"""
        merger = Merger(top_n=3)
        items = [
            _make_candidate(
                title=f"Item {i}",
                url=f"https://a.com/{i}",
                source_weight=float(i),
                topic_weight=1.0,
                keyword_bonus=0.0,
            )
            for i in range(3)
        ]
        result = merger.merge(items, use_new_scoring=True)
        for item in result:
            assert hasattr(item, "final_score")
            assert item.final_score is not None


class TestMergerLegacyRegression:
    """use_new_scoring=False 保持旧行为不变的回归测试"""

    def test_groups_by_category_legacy(self, sample_items_v2):
        merger = Merger(top_n=5)
        result = merger.merge(sample_items_v2, period="morning", use_new_scoring=False)
        assert set(result.keys()) == {"ai", "game", "tool"}

    def test_sorts_desc_legacy(self, sample_items_v2):
        merger = Merger(top_n=5)
        result = merger.merge(sample_items_v2, period="morning", use_new_scoring=False)
        for items in result.values():
            if items:
                scores = [item.source_score for item in items]
                assert scores == sorted(scores, reverse=True)

    def test_top_n_limit_legacy(self, sample_items_v2):
        merger = Merger(top_n=5)
        result = merger.merge(sample_items_v2, period="morning", use_new_scoring=False)
        for items in result.values():
            assert len(items) <= 5

    def test_empty_input_legacy(self):
        merger = Merger(top_n=5)
        result = merger.merge([], period="morning", use_new_scoring=False)
        assert result == {"ai": [], "game": [], "tool": []}

    def test_each_source_has_at_least_one_legacy(self, sample_items_v2):
        """每源保底规则在旧模式仍然生效"""
        merger = Merger(top_n=5)
        result = merger.merge(sample_items_v2, period="morning", use_new_scoring=False)

        for category, items in result.items():
            if not items:
                continue
            input_sources = {item.source for item in sample_items_v2 if item.category == category}
            for src in input_sources:
                assert any(item.source == src for item in items), (
                    f"Category {category}: source {src} missing from result"
                )

    def test_default_behavior_is_legacy(self, sample_items_v2):
        """默认（不传 use_new_scoring）使用旧行为"""
        merger = Merger(top_n=5)
        result = merger.merge(sample_items_v2, period="morning")
        # 旧行为返回 dict
        assert isinstance(result, dict)
        assert set(result.keys()) == {"ai", "game", "tool"}


class TestSourceWeightsConstants:
    """验证评分常量"""

    def test_source_weights_values(self):
        assert SOURCE_WEIGHTS["huggingface"] == 4.0
        assert SOURCE_WEIGHTS["qbitai"] == 3.0
        assert DEFAULT_AI_SOURCE_WEIGHT == 3.0
        assert DEFAULT_OTHER_SOURCE_WEIGHT == 2.0

    def test_topic_weights_values(self):
        assert TOPIC_WEIGHTS["model_release"] == 3.0
        assert TOPIC_WEIGHTS["agent_workflow"] == 2.5
        assert TOPIC_WEIGHTS["developer_tooling"] == 2.0
        assert TOPIC_WEIGHTS["research_benchmark"] == 2.0
        assert TOPIC_WEIGHTS["infrastructure"] == 1.5
        assert TOPIC_WEIGHTS["application_case"] == 1.0
        assert DEFAULT_TOPIC_WEIGHT == 1.0

    def test_keyword_bonus_value(self):
        assert KEYWORD_BONUS == 0.5
