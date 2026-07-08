from dataclasses import dataclass
from typing import Optional


@dataclass
class CandidateItem:
    title: str
    url: str
    summary: str
    source: str
    category: str  # "ai" | "game" | "tool"
    published_at: str = ""  # yyyy-mm-dd
    fetched_at: str = ""  # ISO format
    canonical_key: str = ""  # domain+path, no query/fragment
    ingest_run_id: str = ""  # 哪轮 ingest 产出的
    topic: Optional[str] = None
    topic_confidence: Optional[float] = None
    source_weight: Optional[float] = None
    topic_weight: Optional[float] = None
    keyword_bonus: Optional[float] = None
    final_score: Optional[float] = None

    @staticmethod
    def make_canonical_key(url: str) -> str:
        """从 URL 提取 canonical_key：domain+path，去掉 query string 和 fragment"""
        from urllib.parse import urlparse

        parsed = urlparse(url)
        return f"{parsed.netloc}{parsed.path}"
