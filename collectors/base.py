from dataclasses import dataclass, field
from typing import Literal
import time

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

    @property
    def final_score(self) -> float:
        """Combined score = source heat score + time decay bonus"""
        return self.source_score + time_decay_bonus(self.timestamp)


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


def normalize_rank_score(rank: int, total: int = 10) -> float:
    """Convert rank to 0-10 score: 1st = 10, proportional decrease"""
    if total <= 1:
        return 10.0
    return max(0.0, 10.0 - (rank - 1) * (10.0 / (total - 1)))
