from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, delete, func, select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload, sessionmaker

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
from app.publication.public_api import (
    ArticlePage,
    ArticlePublic,
    DigestItemPublic,
    DigestPublic,
    GitHubProjectPublic,
    PublicationUnavailableError,
    SourcePublic,
)


def _as_utc(value: str | datetime | None) -> datetime | None:
    if not value:
        return None
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _local_day_bounds(day: date, tz: str) -> tuple[datetime, datetime]:
    """将 API 的当地自然日转换为数据库使用的 UTC 半开区间。"""
    local_zone = ZoneInfo(tz)
    start = datetime.combine(day, time.min, tzinfo=local_zone)
    end = datetime.combine(day.fromordinal(day.toordinal() + 1), time.min, tzinfo=local_zone)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def _as_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _public_source(source: Source) -> SourcePublic:
    return SourcePublic(
        name=source.name,
        display_name=source.display_name,
        site_url=source.site_url,
    )


def _public_article(article: Article) -> ArticlePublic:
    return ArticlePublic(
        id=article.id,
        title=article.title,
        original_url=article.original_url,
        category=article.category,
        topic=article.topic,
        summary=article.source_summary or "",
        published_at=_as_iso(article.published_at) if article.published_at else None,
        fetched_at=_as_iso(article.fetched_at),
        source=_public_source(article.source),
    )


@dataclass(frozen=True)
class PublicationCleanupResult:
    """发布库清理的阶段性结果，用于调度审计和状态序列测试。"""

    marked_expired_article_ids: tuple[int, ...]
    deleted_digest_items: int
    deleted_github_projects: int
    deleted_digests: int
    deleted_article_ids: tuple[int, ...]


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

    def list_public_articles(
        self,
        *,
        start_date: date,
        end_date: date,
        tz: str,
        page: int,
        page_size: int,
        source_name: str | None = None,
    ) -> ArticlePage:
        """返回按当地采集日筛选、且只含已发布内容的稳定分页结果。"""
        start_at, _ = _local_day_bounds(start_date, tz)
        _, end_at = _local_day_bounds(end_date, tz)
        filters = [
            Article.visibility == "published",
            Article.fetched_at >= start_at,
            Article.fetched_at < end_at,
        ]
        if source_name is not None:
            filters.append(Source.name == source_name)

        try:
            with self._sessions() as session:
                total = session.scalar(
                    select(func.count(Article.id)).join(Article.source).where(*filters)
                )
                articles = session.scalars(
                    select(Article)
                    .join(Article.source)
                    .options(selectinload(Article.source))
                    .where(*filters)
                    .order_by(
                        func.coalesce(Article.published_at, Article.fetched_at).desc(),
                        Article.id.asc(),
                    )
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                ).all()
                return ArticlePage(
                    items=[_public_article(article) for article in articles],
                    page=page,
                    page_size=page_size,
                    total=total or 0,
                )
        except SQLAlchemyError as exc:
            # 对外仅暴露稳定错误码，连接信息只允许由路由侧按异常类型记录。
            raise PublicationUnavailableError() from exc

    def list_public_sources(
        self, *, start_date: date, end_date: date, tz: str
    ) -> list[SourcePublic]:
        """返回窗口内仍关联公开文章的来源，不以来源启用状态过滤历史内容。"""
        start_at, _ = _local_day_bounds(start_date, tz)
        _, end_at = _local_day_bounds(end_date, tz)
        try:
            with self._sessions() as session:
                sources = session.scalars(
                    select(Source)
                    .join(Source.articles)
                    .where(
                        Article.visibility == "published",
                        Article.fetched_at >= start_at,
                        Article.fetched_at < end_at,
                    )
                    .distinct()
                    .order_by(Source.display_name.asc(), Source.name.asc())
                ).all()
                return [_public_source(source) for source in sources]
        except SQLAlchemyError as exc:
            raise PublicationUnavailableError() from exc

    def cleanup_expired_publication(
        self, *, local_today: date, tz: str
    ) -> PublicationCleanupResult:
        """在单一事务内清理窗口外日报，避免保留日报出现悬空关联。"""
        window_start = local_today - timedelta(days=9)
        cutoff, _ = _local_day_bounds(window_start, tz)
        try:
            with self._sessions.begin() as session:
                expired_digest_ids = list(
                    session.scalars(select(Digest.id).where(Digest.digest_date < window_start))
                )
                retained_digest_ids = select(Digest.id).where(
                    Digest.digest_date >= window_start,
                    Digest.digest_date <= local_today,
                )
                expired_article_ids = list(
                    session.scalars(
                        select(Article.id).where(
                            Article.fetched_at < cutoff,
                            ~Article.digest_items.any(
                                DigestItem.digest_id.in_(retained_digest_ids)
                            ),
                        )
                    )
                )
                if expired_article_ids:
                    session.execute(
                        update(Article)
                        .where(Article.id.in_(expired_article_ids))
                        .values(visibility="expired")
                    )
                if expired_digest_ids:
                    deleted_projects = (
                        session.execute(
                            delete(DigestGitHubProject).where(
                                DigestGitHubProject.digest_id.in_(expired_digest_ids)
                            )
                        ).rowcount
                        or 0
                    )
                    deleted_items = (
                        session.execute(
                            delete(DigestItem).where(DigestItem.digest_id.in_(expired_digest_ids))
                        ).rowcount
                        or 0
                    )
                    deleted_digests = (
                        session.execute(
                            delete(Digest).where(Digest.id.in_(expired_digest_ids))
                        ).rowcount
                        or 0
                    )
                else:
                    deleted_projects = deleted_items = deleted_digests = 0
                if expired_article_ids:
                    session.execute(delete(Article).where(Article.id.in_(expired_article_ids)))
                return PublicationCleanupResult(
                    marked_expired_article_ids=tuple(expired_article_ids),
                    deleted_digest_items=deleted_items,
                    deleted_github_projects=deleted_projects,
                    deleted_digests=deleted_digests,
                    deleted_article_ids=tuple(expired_article_ids),
                )
        except SQLAlchemyError as exc:
            raise PublicationUnavailableError() from exc

    def get_public_digest(self, digest_date: date, *, local_today: date) -> DigestPublic | None:
        """读取保留窗口内的公开日报；关联文章不可公开时整份日报均不可见。"""
        window_start = local_today - timedelta(days=9)
        try:
            with self._sessions() as session:
                digest = session.scalar(
                    select(Digest)
                    .options(
                        selectinload(Digest.items)
                        .selectinload(DigestItem.article)
                        .selectinload(Article.source),
                        selectinload(Digest.github_projects),
                    )
                    .where(
                        Digest.digest_date == digest_date,
                        Digest.digest_date >= window_start,
                        Digest.digest_date <= local_today,
                        Digest.status == "published",
                        ~Digest.items.any(
                            DigestItem.article.has(Article.visibility != "published")
                        ),
                    )
                    .order_by(Digest.version.desc())
                )
                if digest is None or any(
                    item.article.visibility != "published" for item in digest.items
                ):
                    return None
                return DigestPublic(
                    date=digest.digest_date.isoformat(),
                    version=digest.version,
                    published_at=_as_iso(digest.published_at),
                    daily_judgement=digest.daily_judgement,
                    items=[
                        DigestItemPublic(
                            position=item.position,
                            core_summary=item.core_summary,
                            importance=item.importance,
                            trend=item.trend,
                            topic_label=item.topic_label,
                            article=_public_article(item.article),
                        )
                        for item in sorted(digest.items, key=lambda item: item.position)
                    ],
                    github_projects=[
                        GitHubProjectPublic(
                            position=project.position,
                            full_name=project.full_name,
                            recommendation=project.recommendation,
                        )
                        for project in sorted(
                            digest.github_projects, key=lambda project: project.position
                        )
                    ],
                )
        except SQLAlchemyError as exc:
            raise PublicationUnavailableError() from exc

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
