import time
import pytest
from aggregator.merger import Merger
from collectors.base import HotItem


class TestMerger:
    def test_dedup_by_url_keeps_higher_score(self, sample_items):
        """URL dedup keeps the item with higher source_score"""
        merger = Merger(top_n=5)
        result = merger.merge(sample_items)
        ai_items = result["ai"]
        titles = [item.title for item in ai_items]
        assert "AI Paper A" in titles
        assert "AI Paper A dup" not in titles

    def test_groups_by_category(self, sample_items):
        """Groups results by category dict"""
        merger = Merger(top_n=5)
        result = merger.merge(sample_items)
        assert set(result.keys()) == {"ai", "game", "device"}
        assert all(item.category == "ai" for item in result["ai"])
        assert all(item.category == "game" for item in result["game"])
        assert all(item.category == "device" for item in result["device"])

    def test_sorts_by_final_score_desc(self, sample_items):
        """Each category sorted by final_score descending"""
        merger = Merger(top_n=5)
        result = merger.merge(sample_items)
        for cat_items in result.values():
            scores = [item.final_score for item in cat_items]
            assert scores == sorted(scores, reverse=True)

    def test_top_n_limit(self, sample_items):
        """Each category capped at top_n items"""
        merger = Merger(top_n=2)
        result = merger.merge(sample_items)
        for cat_items in result.values():
            assert len(cat_items) <= 2

    def test_empty_input(self):
        """Empty input returns empty dict with all categories"""
        merger = Merger(top_n=5)
        result = merger.merge([])
        assert result == {"ai": [], "game": [], "device": []}

    def test_single_category(self):
        """Only one category of data"""
        now = time.time()
        items = [
            HotItem("AI 1", "https://x.com/1", "", "huggingface", "ai", 8.0, now),
            HotItem("AI 2", "https://x.com/2", "", "rss", "ai", 5.0, now),
        ]
        merger = Merger(top_n=5)
        result = merger.merge(items)
        assert len(result["ai"]) == 2
        assert result["game"] == []
        assert result["device"] == []
