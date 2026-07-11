"""Task 2: time_policy 失败测试 — 模块/接口不存在时预期失败。"""

from datetime import datetime

import pytest


def test_module_importable():
    """验证模块可导入 — 实现前应失败 (ModuleNotFoundError)。"""
    from app.content.time_policy import (  # noqa: F401
        candidate_effective_at,
        freshness_score,
        is_today,
    )


@pytest.mark.parametrize(("age", "score"), [
    (0, 3.0),
    (12, 3.0),
    (24, 3.0),
    (24.01, 1.5),
    (36, 1.5),
    (48, 1.5),
    (48.01, 0.5),
    (60, 0.5),
    (72, 0.5),
])
def test_freshness_boundaries(age, score):
    """freshness_score 的固定分段边界。"""
    from app.content.time_policy import freshness_score

    assert freshness_score(age) == score


def test_effective_time_falls_back_to_fetched_at():
    """published_at 为空时回退到 fetched_at。"""
    from app.content.time_policy import candidate_effective_at
    from app.pipeline.candidate import CandidateItem

    item = CandidateItem(
        title="T", url="https://x", summary="S", source="x", category="ai",
        published_at="", fetched_at="2026-07-10T08:00:00+08:00",
    )
    value, reason = candidate_effective_at(item)
    assert value is not None
    assert "2026-07-10" in value.isoformat()
    assert reason == "fetched_at"


def test_effective_time_uses_published_at():
    """published_at 有效时直接使用。"""
    from app.content.time_policy import candidate_effective_at
    from app.pipeline.candidate import CandidateItem

    item = CandidateItem(
        title="T", url="https://x", summary="S", source="x", category="ai",
        published_at="2026-07-10T09:00:00+08:00",
        fetched_at="2026-07-10T08:00:00+08:00",
    )
    value, reason = candidate_effective_at(item)
    assert value.isoformat() == "2026-07-10T09:00:00+08:00"
    assert reason == "rss"


def test_effective_time_returns_none_for_empty():
    """published_at 和 fetched_at 都为空时返回 None。"""
    from app.content.time_policy import candidate_effective_at
    from app.pipeline.candidate import CandidateItem

    item = CandidateItem(
        title="T", url="https://x", summary="S", source="x", category="ai",
    )
    value, reason = candidate_effective_at(item)
    assert value is None
    assert reason == "unknown"


def test_is_today_true_for_same_date():
    """同一自然日在 Asia/Shanghai 被判定为今天。"""
    from app.content.time_policy import is_today

    tz = "Asia/Shanghai"
    now = datetime(2026, 7, 11, 9, 0, 0)
    today_early = datetime(2026, 7, 11, 0, 30, 0)
    today_late = datetime(2026, 7, 11, 23, 30, 0)

    assert is_today(today_early, now, tz) is True
    assert is_today(today_late, now, tz) is True


def test_is_today_false_for_yesterday():
    """昨天被判定为非今天。"""
    from app.content.time_policy import is_today

    tz = "Asia/Shanghai"
    now = datetime(2026, 7, 11, 9, 0, 0)
    yesterday = datetime(2026, 7, 10, 23, 59, 0)

    assert is_today(yesterday, now, tz) is False


def test_naive_datetime_parsed_correctly():
    """没有时区的日期字符串按 yyyy-mm-dd 解析为当天零点（Asia/Shanghai）。"""
    from app.content.time_policy import candidate_effective_at
    from app.pipeline.candidate import CandidateItem

    item = CandidateItem(
        title="T", url="https://x", summary="S", source="x", category="ai",
        published_at="2026-07-10",
        fetched_at="2026-07-10T08:00:00+08:00",
    )
    value, reason = candidate_effective_at(item)
    assert value is not None
    assert reason == "legacy_date"


def test_freshness_negative_returns_zero():
    """负值年龄返回 0.0（防御性处理）。"""
    from app.content.time_policy import freshness_score

    assert freshness_score(-1) == 0.0
    assert freshness_score(-100) == 0.0


def test_is_today_with_aware_timezone():
    """带时区的 datetime 也能正确判断今天。"""
    from datetime import timedelta, timezone

    from app.content.time_policy import is_today

    cst = timezone(timedelta(hours=8))
    now = datetime(2026, 7, 11, 9, 0, 0)
    value = datetime(2026, 7, 11, 3, 0, 0, tzinfo=cst)
    assert is_today(value, now) is True


def test_effective_at_with_z_suffix():
    """ISO 字符串带 Z 后缀也能正确解析。"""
    from app.content.time_policy import candidate_effective_at
    from app.pipeline.candidate import CandidateItem

    item = CandidateItem(
        title="T", url="https://x", summary="S", source="x", category="ai",
        published_at="2026-07-10T09:00:00Z",
    )
    value, reason = candidate_effective_at(item)
    assert value is not None
    assert reason == "rss"
