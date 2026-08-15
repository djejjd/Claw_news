from __future__ import annotations

from datetime import datetime

from app.pipeline.candidate import CandidateItem
from app.publication.source_registry import SourceRegistryAdapter
from app.publication.store import PublicationStore


class Publisher:
    """将内部候选和日报结果写入发布库，不参与消息投递。"""

    def __init__(self, store: PublicationStore):
        self.store = store

    @classmethod
    def from_config(cls, config) -> Publisher | None:
        if getattr(config, "publication_enabled", False) is not True:
            return None
        database_url = getattr(config, "publication_database_url", None)
        if not database_url:
            raise ValueError("enabled publication requires publication_database_url")
        return cls(PublicationStore(database_url))

    def publish_candidates(
        self, candidates: list[CandidateItem], feed_configuration: dict | None
    ) -> int:
        self.store.publish_sources(
            SourceRegistryAdapter.from_feed_configuration(feed_configuration)
        )
        return self.store.publish_articles(candidates)

    def digest_exists(self, digest_date: str) -> bool:
        return self.store.digest_exists(digest_date, version=1)

    def publish_digest(
        self,
        *,
        digest_date: str,
        published_at: datetime,
        headline_items: list[dict],
        selected: list[CandidateItem],
        daily_judgement: str,
        github_projects: list[dict],
    ) -> None:
        by_url = {candidate.url: candidate for candidate in selected}
        items = []
        for position, item in enumerate(headline_items, start=1):
            candidate = by_url.get(item["url"])
            if candidate is None:
                continue
            items.append(
                {
                    "canonical_key": candidate.canonical_key
                    or CandidateItem.make_canonical_key(candidate.url),
                    "position": position,
                    "core_summary": item["core_summary"],
                    "importance": item["importance"],
                    "trend": item["trend"],
                    "topic_label": item.get("topic_label"),
                    "relevance": item.get("relevance"),
                }
            )
        self.store.publish_articles(selected)
        self.store.publish_digest(
            digest_date=digest_date,
            version=1,
            published_at=published_at,
            daily_judgement=daily_judgement,
            items=items,
            github_projects=github_projects,
        )
