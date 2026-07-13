"""时间工具 — freshness_score、文章有效时间、今日判断。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Tuple

from app.pipeline.candidate import CandidateItem

# 固定 freshness 分段（设计第 9 节，不可调整）
_FRESHNESS_TABLE = [
    (24.0, 3.0),
    (48.0, 1.5),
    (72.0, 0.5),
]


def freshness_score(age_hours: float) -> float:
    """按文章年龄(小时)返回固定分段 freshness_score。

    age_hours <= 24  → 3.0
    24 < age <= 48   → 1.5
    48 < age <= 72   → 0.5
    age > 72 或负值  → 0.0
    """
    if age_hours < 0:
        return 0.0
    for boundary, score in _FRESHNESS_TABLE:
        if age_hours <= boundary:
            return score
    return 0.0


def candidate_effective_at(
    item: CandidateItem,
) -> Tuple[Optional[datetime], str]:
    """返回文章的有效发布时间和来源标识。

    yyyy-mm-dd 日期先于 ISO 时间检测（避免 Python 3.11+ fromisoformat 歧义），
    然后按 ISO → fetched_at 回退。
    返回值：(datetime | None, reason: rss | legacy_date | fetched_at | unknown)
    """
    # 1. published_at 为 yyyy-mm-dd 日期（先于 ISO，避免 Python 3.11+ 解析日期为 datetime）
    pub = (item.published_at or "").strip()
    if pub and len(pub) == 10 and pub[4] == "-" and pub[7] == "-":
        try:
            dt = datetime.strptime(pub, "%Y-%m-%d")
            return dt, "legacy_date"
        except ValueError:
            pass

    # 2. published_at 为完整 ISO 时间
    if pub:
        try:
            dt = datetime.fromisoformat(pub)
            return dt, "rss"
        except ValueError:
            pass

    # 3. fetched_at 回退
    fetched = (item.fetched_at or "").strip()
    if fetched:
        try:
            dt = datetime.fromisoformat(fetched)
            return dt, "fetched_at"
        except ValueError:
            pass

    return None, "unknown"


def is_today(value: datetime, now: datetime, tz_name: str = "Asia/Shanghai") -> bool:
    """判断 value 和 now 是否在 tz_name 时区的同一自然日。

    naive datetime 视为已在目标时区；aware datetime 先转 UTC 再加偏移。
    """
    from datetime import timedelta

    offset_hours = _tz_offset_hours(tz_name)

    def _to_local(dt: datetime) -> datetime:
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            dt = dt + timedelta(hours=offset_hours)
        # naive dt: already in local time
        return dt

    local_value = _to_local(value)
    local_now = _to_local(now)
    return local_value.date() == local_now.date()


def _tz_offset_hours(tz_name: str) -> int:
    """简单时区偏移映射，避免 zoneinfo 依赖。"""
    offsets = {
        "Asia/Shanghai": 8,
        "Asia/Tokyo": 9,
        "UTC": 0,
    }
    return offsets.get(tz_name, 8)
