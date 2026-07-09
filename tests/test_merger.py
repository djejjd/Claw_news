from datetime import date as _date
from datetime import timedelta

from aggregator.merger import (
    DEFAULT_SOURCE_WEIGHT,
    SOURCE_WEIGHTS,
    Merger,
    compute_final_score,
    compute_source_score,
    position_score,
)
from app.pipeline.candidate import CandidateItem
from collectors.base import HotItem, time_gravity

# =============================================================================
# Helpers
# =============================================================================

_TODAY = _date.today().isoformat()
_YESTERDAY = (_date.today() - timedelta(days=1)).isoformat()
_OLD_DATE = (_date.today() - timedelta(days=3)).isoformat()


def _make_candidate(**kwargs):
    data = {
        "title": "Test Item",
        "url": "https://example.com/1",
        "source": "qbitai",
        "category": "ai",
        "summary": "A test item",
        "published_at": _TODAY,
        "topic": "model_release",
        "source_weight": None,
    }
    data.update(kwargs)
    return CandidateItem(**data)


def _make_hotitem(**kwargs):
    data = {
        "title": "Test Item",
        "url": "https://example.com/1",
        "source": "qbitai",
        "category": "ai",
        "source_score": 5.0,
        "pub_date": _TODAY,
    }
    data.update(kwargs)
    return HotItem(**data)


# =============================================================================
# Legacy scoring (unchanged)
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
        assert score == 11.0

    def test_rss_no_keyword_old(self):
        item = HotItem("t", "", "", "yystv", "game", 5.0, keyword_hit=False, pub_date="2026-05-10")
        score = compute_source_score(item, position=5, period="morning")
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
        merger = Merger(top_n=5)
        result = merger.merge(sample_items_v2, period="morning")
        for category, items in result.items():
            if not items:
                continue
            input_sources = {item.source for item in sample_items_v2 if item.category == category}
            for src in input_sources:
                assert any(item.source == src for item in items), (
                    f"Category {category}: source {src} missing from result"
                )

    def test_time_gravity_import(self):
        assert callable(time_gravity)


# =============================================================================
# New scoring: source_weight + time_gravity
# =============================================================================


class TestComputeFinalScore:
    def test_basic_calculation(self):
        """source_weight + time_gravity (today=3.0)"""
        item = _make_candidate(source="qbitai", source_weight=3.0, published_at=_TODAY)
        score = compute_final_score(item)
        # sw=3.0 + tg(today)=3.0 = 6.0
        assert score == 6.0

    def test_known_source_uses_lookup(self):
        """已知 source 使用 SOURCE_WEIGHTS 中的值"""
        item = _make_candidate(source="leiphone", source_weight=None, published_at=_TODAY)
        score = compute_final_score(item)
        assert score == 6.0  # sw=3.0 + tg=3.0

    def test_unknown_source_default(self):
        """未知 source 使用 DEFAULT_SOURCE_WEIGHT"""
        item = _make_candidate(
            source="unknown_source_xyz", source_weight=None, published_at=_TODAY,
        )
        score = compute_final_score(item)
        assert score == 5.0  # sw=2.0 + tg=3.0

    def test_old_pub_date_decays(self):
        """3 天前的 pub_date 应衰减"""
        item = _make_candidate(source="qbitai", source_weight=3.0, published_at=_OLD_DATE)
        score = compute_final_score(item)
        # age=72h, flat_top=24h: effective_age=48h
        # tg = 3.0 / (48+2)^0.6 ≈ 3.0 / 10.4 ≈ 0.3
        # sw=3.0 + tg≈0.3 ≈ 3.3
        assert score < 4.0

    def test_huggingface_source_weight(self):
        item = _make_candidate(source="huggingface", source_weight=None, published_at=_TODAY)
        score = compute_final_score(item)
        assert score == 7.0  # sw=4.0 + tg=3.0

    def test_all_default_sources_have_weights(self):
        """所有 feeds.yaml 中的默认源都有权重配置"""
        expected_sources = {
            "qbitai", "leiphone", "jiqizhixin", "meituan_tech",
            "sspai", "ithome", "appinn", "cloudflare_cn",
            "yystv", "gcores", "chuapp", "indienova", "eurogamer",
            "huggingface",
        }
        for src in expected_sources:
            assert src in SOURCE_WEIGHTS, f"Missing source weight for: {src}"
            assert SOURCE_WEIGHTS[src] >= 2.0, f"Source {src} weight too low"


# =============================================================================
# New scoring path with category guarantee
# =============================================================================


class TestMergerNewScoring:
    def test_returns_sorted_list(self):
        merger = Merger(top_n=5)
        items = [
            _make_candidate(title="Low", url="https://a.com/low", source_weight=1.0, category="ai"),
            _make_candidate(title="High", url="https://a.com/high", source_weight=3.0, category="ai"),
            _make_candidate(title="Mid", url="https://a.com/mid", source_weight=2.0, category="ai"),
        ]
        result = merger.merge(items, use_new_scoring=True)
        scores = [item.final_score for item in result]
        assert scores == sorted(scores, reverse=True)

    def test_respects_top_n(self):
        merger = Merger(top_n=3)
        items = [
            _make_candidate(title=f"Item {i}", url=f"https://a.com/{i}", source_weight=float(i), category="ai")
            for i in range(8)
        ]
        result = merger.merge(items, use_new_scoring=True)
        assert len(result) == 3

    def test_category_guarantee_each_has_at_least_one(self):
        """P0: 每类至少 1 条出现在结果中"""
        merger = Merger(top_n=6)
        items = [
            _make_candidate(title="AI 1", url="https://a.com/1", source_weight=3.0, category="ai"),
            _make_candidate(title="Tool 1", url="https://t.com/1", source_weight=3.0, category="tool", source="sspai"),
            _make_candidate(title="Game 1", url="https://g.com/1", source_weight=3.0, category="game", source="yystv"),
            _make_candidate(title="AI 2", url="https://a.com/2", source_weight=2.0, category="ai"),
            _make_candidate(title="AI 3", url="https://a.com/3", source_weight=2.0, category="ai"),
            _make_candidate(title="AI 4", url="https://a.com/4", source_weight=2.0, category="ai"),
        ]
        result = merger.merge(items, use_new_scoring=True)
        cats = {item.category for item in result}
        assert cats == {"ai", "tool", "game"}

    def test_missing_category_not_forced(self):
        """某类无候选时只输出有的分类，不强行补空"""
        merger = Merger(top_n=5)
        items = [
            _make_candidate(title="AI 1", url="https://a.com/1", source_weight=3.0, category="ai"),
            _make_candidate(title="AI 2", url="https://a.com/2", source_weight=2.0, category="ai"),
        ]
        result = merger.merge(items, use_new_scoring=True)
        cats = {item.category for item in result}
        assert cats == {"ai"}

    def test_no_duplicate_in_guarantee_round(self):
        """保底轮选过的 URL 不会在竞争轮重复出现"""
        merger = Merger(top_n=5)
        items = [
            _make_candidate(title="AI 1", url="https://a.com/1", source_weight=3.0, category="ai"),
            _make_candidate(title="AI 2", url="https://a.com/2", source_weight=2.5, category="ai"),
            _make_candidate(title="Tool 1", url="https://t.com/1", source_weight=2.0, category="tool", source="sspai"),
            _make_candidate(title="Game 1", url="https://g.com/1", source_weight=1.5, category="game", source="yystv"),
        ]
        result = merger.merge(items, use_new_scoring=True)
        urls = [item.url for item in result]
        assert len(urls) == len(set(urls))  # no duplicates

    def test_empty_input(self):
        merger = Merger(top_n=5)
        result = merger.merge([], use_new_scoring=True)
        assert result == []

    def test_dedup_keeps_higher_score(self):
        merger = Merger(top_n=5)
        items = [
            _make_candidate(title="Low", url="https://dup.com/1", source_weight=1.0, category="ai"),
            _make_candidate(title="High", url="https://dup.com/1", source_weight=3.0, category="ai"),
        ]
        result = merger.merge(items, use_new_scoring=True)
        kept = next(item for item in result if item.url == "https://dup.com/1")
        assert kept.title == "High"


class TestMergerLegacyRegression:
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

    def test_default_behavior_is_legacy(self, sample_items_v2):
        merger = Merger(top_n=5)
        result = merger.merge(sample_items_v2, period="morning")
        assert isinstance(result, dict)
        assert set(result.keys()) == {"ai", "game", "tool"}


class TestSourceWeightsConstants:
    def test_source_weights_values(self):
        assert SOURCE_WEIGHTS["huggingface"] == 4.0
        assert SOURCE_WEIGHTS["qbitai"] == 3.0
        assert DEFAULT_SOURCE_WEIGHT == 2.0

    def test_all_thirteen_default_sources_configured(self):
        """13 个默认 feed 源全部有 SOURCE_WEIGHTS 配置"""
        expected = {
            "qbitai", "leiphone", "jiqizhixin", "meituan_tech",
            "sspai", "ithome", "appinn", "cloudflare_cn",
            "yystv", "gcores", "chuapp", "indienova", "eurogamer",
            "huggingface",
        }
        for src in expected:
            assert src in SOURCE_WEIGHTS, f"Missing: {src}"
