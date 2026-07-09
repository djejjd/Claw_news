"""Tests for app/github_ranking — scoring, exposure penalty, recommendations."""
from datetime import date, timedelta

from app.github_ranking import rank_and_recommend
from collectors.github import GitHubRepoItem


_TODAY = date.today().isoformat()


def _make_item(**kwargs) -> GitHubRepoItem:
    data = {
        "full_name": "owner/repo",
        "url": "https://github.com/owner/repo",
        "description": "An AI tool for developers",
        "stars": 1000,
        "forks": 200,
        "watchers": 50,
        "language": "Python",
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2026-07-08T00:00:00Z",
        "pushed_at": "2026-07-08T00:00:00Z",
        "matched_topics": ["llm"],
        "matched_keywords": ["llm"],
    }
    data.update(kwargs)
    return GitHubRepoItem(**data)


class TestActivityScore:
    def test_recent_push_scores_high(self):
        today = date.today().isoformat()
        item = _make_item(pushed_at=f"{today}T00:00:00Z")
        result = rank_and_recommend([item], {}, top_n=1)
        assert result[0]["activity"] >= 2.9

    def test_old_push_scores_low(self):
        old = (date.today() - timedelta(days=90)).isoformat()
        item = _make_item(pushed_at=f"{old}T00:00:00Z")
        result = rank_and_recommend([item], {}, top_n=1)
        assert result[0]["activity"] < 1.0


class TestPopularityScore:
    def test_high_stars_scores_high(self):
        item_low = _make_item(full_name="a/b", stars=10)
        item_high = _make_item(full_name="c/d", stars=10000)

        result = rank_and_recommend([item_low, item_high], {}, top_n=2)
        assert result[0]["item"].full_name == "c/d"
        assert result[0]["popularity"] > result[1]["popularity"]


class TestExposurePenalty:
    def test_exposed_today_gets_strong_penalty(self):
        today = date.today()
        item = _make_item(full_name="owner/exposed")
        exposure = {"owner/exposed": today}

        result = rank_and_recommend([item], exposure, top_n=1)
        assert result[0]["penalty"] == -3.0

    def test_exposed_last_week_gets_light_penalty(self):
        week_ago = date.today() - timedelta(days=5)
        item = _make_item(full_name="owner/old")
        exposure = {"owner/old": week_ago}

        result = rank_and_recommend([item], exposure, top_n=1)
        assert result[0]["penalty"] == -0.5

    def test_never_exposed_no_penalty(self):
        item = _make_item(full_name="owner/new")
        result = rank_and_recommend([item], {}, top_n=1)
        assert result[0]["penalty"] == 0.0

    def test_strong_project_can_still_appear_with_penalty(self):
        """强项目即使近期曝光过，如果有足够高的 activity+popularity 仍可入围"""
        today = date.today()
        strong = _make_item(
            full_name="owner/strong",
            stars=50000,
            forks=10000,
            watchers=5000,
            pushed_at=f"{today.isoformat()}T00:00:00Z",
        )
        weak = _make_item(
            full_name="owner/weak",
            stars=50,
            forks=5,
            watchers=3,
            pushed_at=(today - timedelta(days=30)).isoformat(),
        )
        exposure = {"owner/strong": today, "owner/weak": today}

        result = rank_and_recommend([strong, weak], exposure, top_n=2)
        # Strong project should still rank well despite penalty
        assert result[0]["item"].full_name == "owner/strong"

    def test_ordinary_projects_rotate_with_exposure(self):
        """普通项目在曝光后应被未曝光的新项目超越"""
        today = date.today()
        exposed = _make_item(
            full_name="owner/exposed",
            stars=500,
            pushed_at=f"{today.isoformat()}T00:00:00Z",
        )
        fresh = _make_item(
            full_name="owner/fresh",
            stars=500,
            pushed_at=f"{today.isoformat()}T00:00:00Z",
        )
        exposure = {"owner/exposed": today}

        result = rank_and_recommend([exposed, fresh], exposure, top_n=2)
        # Fresh should outrank exposed (exposed has -3.0 penalty)
        assert result[0]["item"].full_name == "owner/fresh"


class TestRecommendationReasons:
    def test_active_project_has_activity_reason(self):
        today = date.today()
        item = _make_item(pushed_at=f"{today.isoformat()}T00:00:00Z")
        result = rank_and_recommend([item], {}, top_n=1)
        assert "近3天活跃更新" in result[0]["recommendation"]

    def test_popular_project_has_popularity_reason(self):
        today = date.today()
        item = _make_item(stars=10000, pushed_at=f"{today.isoformat()}T00:00:00Z")
        result = rank_and_recommend([item], {}, top_n=1)
        assert "社区热度高" in result[0]["recommendation"]

    def test_new_project_has_growth_reason(self):
        today = date.today()
        recent = (date.today() - timedelta(days=10)).isoformat()
        item = _make_item(
            stars=500,
            pushed_at=f"{today.isoformat()}T00:00:00Z",
            created_at=f"{recent}T00:00:00Z",
        )
        result = rank_and_recommend([item], {}, top_n=1)
        assert "新项目快速增长" in result[0]["recommendation"]

    def test_agent_topic_has_agent_reason(self):
        today = date.today()
        item = _make_item(
            matched_topics=["agent"],
            stars=500,  # below 1000 to avoid "关注度上升" overriding
            pushed_at=f"{today.isoformat()}T00:00:00Z",
        )
        result = rank_and_recommend([item], {}, top_n=1)
        assert "AI Agent" in result[0]["recommendation"]

    def test_fallback_reason(self):
        old = (date.today() - timedelta(days=90)).isoformat()
        item = _make_item(
            stars=10,
            pushed_at=f"{old}T00:00:00Z",
            matched_topics=[],
            matched_keywords=[],
        )
        result = rank_and_recommend([item], {}, top_n=1)
        assert result[0]["recommendation"] == "值得关注"


class TestTop3Output:
    def test_returns_at_most_top_n(self):
        today = date.today()
        items = [
            _make_item(
                full_name=f"owner/repo{i}",
                pushed_at=f"{today.isoformat()}T00:00:00Z",
                stars=1000 + i,
            )
            for i in range(10)
        ]
        result = rank_and_recommend(items, {}, top_n=3)
        assert len(result) == 3

    def test_scores_are_descending(self):
        today = date.today()
        items = [
            _make_item(
                full_name=f"owner/repo{i}",
                pushed_at=f"{today.isoformat()}T00:00:00Z",
                stars=(i + 1) * 100,
            )
            for i in range(10)
        ]
        result = rank_and_recommend(items, {}, top_n=5)
        scores = [r["final_score"] for r in result]
        assert scores == sorted(scores, reverse=True)


class TestLowStarFilter:
    def test_low_star_items_are_excluded(self):
        today = date.today()
        items = [
            _make_item(full_name="owner/spam", stars=5, pushed_at=f"{today.isoformat()}T00:00:00Z"),
            _make_item(full_name="owner/good", stars=100, pushed_at=f"{today.isoformat()}T00:00:00Z"),
        ]
        result = rank_and_recommend(items, {}, top_n=2)
        names = [r["item"].full_name for r in result]
        assert "owner/spam" not in names
        assert "owner/good" in names

    def test_all_low_star_returns_empty(self):
        items = [
            _make_item(full_name=f"owner/repo{i}", stars=i)
            for i in range(5)
        ]
        result = rank_and_recommend(items, {}, top_n=3)
        assert result == []

    def test_exactly_at_threshold_is_kept(self):
        today = date.today()
        item = _make_item(full_name="owner/min", stars=10, pushed_at=f"{today.isoformat()}T00:00:00Z")
        result = rank_and_recommend([item], {}, top_n=1)
        assert len(result) == 1
        assert result[0]["item"].full_name == "owner/min"
