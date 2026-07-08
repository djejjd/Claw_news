import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from app.pipeline.candidate import CandidateItem

Category = Literal["ai", "game", "device"]


@dataclass
class HotItem:
    title: str
    url: str
    summary: str
    source: str
    category: Category
    source_score: float  # 0.0-10.0, derived from source popularity/rank
    timestamp: float = field(default_factory=time.time)
    keyword_hit: bool = False  # 是否命中分类关键词
    pub_date: str = ""  # yyyy-mm-dd 发布日期

    @property
    def final_score(self) -> float:
        """Combined score = source heat score + time decay bonus"""
        return self.source_score + time_decay_bonus(self.timestamp)


def time_modifier(pub_date: str, period: str = "morning") -> float:
    """morning: today+yesterday=0, older=-2.0. evening: today=0, yesterday=-1.0, older=-2.0"""
    if not pub_date:
        return 0
    try:
        diff = (date.today() - date.fromisoformat(pub_date)).days
        if period == "morning":
            return 0.0 if diff <= 1 else -2.0
        else:
            if diff == 0:
                return 0.0
            if diff == 1:
                return -1.0
            return -2.0
    except ValueError:
        return 0


def time_decay_bonus(ts: float, now: float | None = None) -> float:
    """24h: +2, 24-48h: +1, 48-72h: 0, then -1 per 12h"""
    if now is None:
        now = time.time()
    age_hours = (now - ts) / 3600
    if age_hours <= 24:
        return 2.0
    if age_hours <= 48:
        return 1.0
    if age_hours <= 72:
        return 0.0
    return -float((age_hours - 72) // 12)


BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def normalize_rank_score(rank: int, total: int = 10) -> float:
    """Convert rank to 0-10 score: 1st = 10, proportional decrease"""
    if total <= 1:
        return 10.0
    return max(0.0, 10.0 - (rank - 1) * (10.0 / (total - 1)))


def hotitem_to_candidate(item: HotItem, ingest_run_id: str = "") -> "CandidateItem":
    """将旧的 HotItem 转换为统一的 CandidateItem"""
    from app.pipeline.candidate import CandidateItem

    return CandidateItem(
        title=item.title,
        url=item.url,
        summary=item.summary,
        source=item.source,
        category=item.category,
        published_at=item.pub_date,
        fetched_at=datetime.fromtimestamp(item.timestamp).isoformat(),
        canonical_key=CandidateItem.make_canonical_key(item.url) if item.url else "",
        ingest_run_id=ingest_run_id,
    )
