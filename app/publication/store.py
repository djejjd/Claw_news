from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.category_policy import normalize_category
from app.pipeline.candidate import CandidateItem
from app.publication.models import (
    Article,
    Base,
    Digest,
    DigestGitHubProject,
    DigestItem,
    Source,
    SourceFeed,
)


def _as_utc(value: str | datetime | None) -> datetime | None:
    if not value:
        return None
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class PublicationStore:
    """发布库写入接口；测试可使用 SQLite，正式运行目标为 PostgreSQL。"""

    def __init__(self, database_url: str):
        self.engine = create_engine(database_url)
        self._sessions = sessionmaker(self.engine, expire_on_commit=False)

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    def healthcheck(self) -> None:
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    def digest_exists(self, digest_date: str, version: int = 1) -> bool:
        """返回指定自然日的发布版本是否已成为内容定版。"""
        digest_day = date.fromisoformat(digest_date)
        with self._sessions() as session:
            return (
                session.scalar(
                    select(Digest.id).where(
                        Digest.digest_date == digest_day,
                        Digest.version == version,
                    )
                )
                is not None
            )

    def publish_sources(self, specs: list[dict]) -> None:
        now = datetime.now(timezone.utc)
        with self._sessions.begin() as session:
            for spec in specs:
                category = normalize_category(spec["default_category"])
                source = session.scalar(select(Source).where(Source.name == spec["name"]))
                if source is None:
                    source = Source(
                        name=spec["name"],
                        display_name=spec.get("display_name") or spec["name"],
                        default_category=category,
                        site_url=spec.get("site_url"),
                        is_enabled=spec.get("is_enabled", True),
                        include_in_new_user_defaults=spec.get(
                            "include_in_new_user_defaults", False
                        ),
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(source)
                    session.flush()
                else:
                    source.display_name = spec.get("display_name") or source.display_name
                    source.default_category = category
                    source.site_url = spec.get("site_url") or source.site_url
                    source.is_enabled = spec.get("is_enabled", source.is_enabled)
                    source.updated_at = now
                for feed_spec in spec.get("feeds", []):
                    feed = session.scalar(
                        select(SourceFeed).where(
                            SourceFeed.source_id == source.id, SourceFeed.url == feed_spec["url"]
                        )
                    )
                    if feed is None:
                        session.add(
                            SourceFeed(
                                source_id=source.id,
                                url=feed_spec["url"],
                                collector_type=feed_spec.get("collector_type", "rss"),
                                strategy=feed_spec.get("strategy", {}),
                            )
                        )

    def publish_articles(self, candidates: list[CandidateItem]) -> int:
        now = datetime.now(timezone.utc)
        with self._sessions.begin() as session:
            for candidate in candidates:
                canonical_key = candidate.canonical_key or CandidateItem.make_canonical_key(
                    candidate.url
                )
                if not canonical_key:
                    raise ValueError("article requires canonical_key")
                source = self._ensure_source(session, candidate.source, candidate.category, now)
                existing = session.scalar(
                    select(Article).where(Article.canonical_key == canonical_key)
                )
                incoming_published = _as_utc(candidate.published_at)
                incoming_fetched = _as_utc(candidate.fetched_at) or now
                if existing is None:
                    session.add(
                        Article(
                            canonical_key=canonical_key,
                            title=candidate.title,
                            original_url=candidate.url,
                            source_id=source.id,
                            category=normalize_category(candidate.category),
                            topic=candidate.topic,
                            topic_confidence=candidate.topic_confidence,
                            source_summary=candidate.summary or "",
                            published_at=incoming_published,
                            fetched_at=incoming_fetched,
                            visibility="published",
                        )
                    )
                    continue
                if self._is_newer(existing, incoming_published, incoming_fetched):
                    existing.title = candidate.title
                    existing.original_url = candidate.url
                    existing.source_id = source.id
                    existing.category = normalize_category(candidate.category)
                    existing.topic = candidate.topic
                    existing.topic_confidence = candidate.topic_confidence
                    existing.published_at = incoming_published
                    existing.fetched_at = incoming_fetched
                    existing.source_summary = candidate.summary or existing.source_summary
            return len(candidates)

    def publish_digest(
        self,
        *,
        digest_date: str,
        version: int,
        published_at: datetime,
        daily_judgement: str,
        items: list[dict],
        github_projects: list[dict],
    ) -> None:
        with self._sessions.begin() as session:
            articles = {}
            for item in items:
                article = session.scalar(
                    select(Article).where(Article.canonical_key == item["canonical_key"])
                )
                if article is None:
                    raise ValueError(f"unknown article: {item['canonical_key']}")
                articles[item["canonical_key"]] = article
            digest_day = date.fromisoformat(digest_date)
            digest = session.scalar(
                select(Digest).where(Digest.digest_date == digest_day, Digest.version == version)
            )
            if digest is None:
                digest = Digest(
                    digest_date=digest_day,
                    version=version,
                    published_at=_as_utc(published_at) or datetime.now(timezone.utc),
                    status="published",
                    daily_judgement=daily_judgement,
                )
                session.add(digest)
                session.flush()
            else:
                session.query(DigestItem).filter_by(digest_id=digest.id).delete()
                session.query(DigestGitHubProject).filter_by(digest_id=digest.id).delete()
                digest.published_at = _as_utc(published_at) or digest.published_at
                digest.daily_judgement = daily_judgement
            for item in items:
                session.add(
                    DigestItem(
                        digest_id=digest.id,
                        article_id=articles[item["canonical_key"]].id,
                        position=item["position"],
                        core_summary=item["core_summary"],
                        importance=item["importance"],
                        trend=item["trend"],
                        topic_label=item.get("topic_label"),
                        relevance=item.get("relevance"),
                    )
                )
            for position, project in enumerate(github_projects, start=1):
                session.add(
                    DigestGitHubProject(
                        digest_id=digest.id,
                        position=position,
                        full_name=project["full_name"],
                        recommendation=project.get("recommendation", ""),
                        final_score=project.get("final_score"),
                    )
                )

    def get_article(self, canonical_key: str) -> Article:
        with self._sessions() as session:
            article = session.scalar(select(Article).where(Article.canonical_key == canonical_key))
            if article is None:
                raise LookupError(canonical_key)
            return article

    def get_source(self, name: str) -> Source:
        with self._sessions() as session:
            source = session.scalar(select(Source).where(Source.name == name))
            if source is None:
                raise LookupError(name)
            return source

    def count_articles(self) -> int:
        with self._sessions() as session:
            return len(session.scalars(select(Article)).all())

    def count_source_feeds(self, source_name: str) -> int:
        with self._sessions() as session:
            source = session.scalar(select(Source).where(Source.name == source_name))
            return len(source.feeds) if source else 0

    def count_digests(self) -> int:
        with self._sessions() as session:
            return len(session.scalars(select(Digest)).all())

    def count_digest_items(self) -> int:
        with self._sessions() as session:
            return len(session.scalars(select(DigestItem)).all())

    @staticmethod
    def _ensure_source(session: Session, name: str, category: str, now: datetime) -> Source:
        source = session.scalar(select(Source).where(Source.name == name))
        if source is None:
            source = Source(
                name=name,
                display_name=name,
                default_category=normalize_category(category),
                created_at=now,
                updated_at=now,
            )
            session.add(source)
            session.flush()
        return source

    @staticmethod
    def _is_newer(
        existing: Article, incoming_published: datetime | None, incoming_fetched: datetime
    ) -> bool:
        existing_published = _as_utc(existing.published_at)
        existing_fetched = _as_utc(existing.fetched_at)
        if incoming_published and (
            existing_published is None or incoming_published > existing_published
        ):
            return True
        if existing_published and incoming_published and incoming_published < existing_published:
            return False
        return existing_fetched is None or incoming_fetched > existing_fetched
