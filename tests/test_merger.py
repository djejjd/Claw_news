from aggregator.merger import Merger, compute_source_score, position_score
from collectors.base import HotItem, time_modifier


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
        item = HotItem("t", "", "", "qbitai", "ai", 5.0, keyword_hit=True, pub_date="2026-05-16")
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
        assert set(result.keys()) == {"ai", "game", "device"}

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
        assert result == {"ai": [], "game": [], "device": []}

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
