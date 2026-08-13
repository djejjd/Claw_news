"""统一的本地业务时间。"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


def local_now(tz_name: str = "Asia/Shanghai") -> datetime:
    """返回指定时区的无时区本地时间，兼容现有数据格式。"""
    if not isinstance(tz_name, str) or not tz_name.strip():
        tz_name = "Asia/Shanghai"
    return datetime.now(ZoneInfo(tz_name)).replace(tzinfo=None)
