from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    default_category: Mapped[str] = mapped_column(String(20))
    site_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    include_in_new_user_defaults: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    feeds: Mapped[list[SourceFeed]] = relationship(back_populates="source")
    articles: Mapped[list[Article]] = relationship(back_populates="source")

    __table_args__ = (CheckConstraint("default_category IN ('ai', 'tool', 'game', 'digital')"),)


class SourceFeed(Base):
    __tablename__ = "source_feeds"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(String(2048))
    collector_type: Mapped[str] = mapped_column(String(80))
    strategy: Mapped[dict] = mapped_column(JSON, default=dict)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_failure_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    source: Mapped[Source] = relationship(back_populates="feeds")

    __table_args__ = (UniqueConstraint("source_id", "url"),)


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_key: Mapped[str] = mapped_column(String(2048), unique=True, index=True)
    title: Mapped[str] = mapped_column(Text)
    original_url: Mapped[str] = mapped_column(String(4096))
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    category: Mapped[str] = mapped_column(String(20))
    topic: Mapped[str | None] = mapped_column(String(120), nullable=True)
    topic_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_summary: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    visibility: Mapped[str] = mapped_column(String(20), default="published")

    source: Mapped[Source] = relationship(back_populates="articles")
    digest_items: Mapped[list[DigestItem]] = relationship(back_populates="article")

    __table_args__ = (
        CheckConstraint("category IN ('ai', 'tool', 'game', 'digital')"),
        CheckConstraint("visibility IN ('published', 'hidden', 'expired')"),
    )


class Digest(Base):
    __tablename__ = "digests"

    id: Mapped[int] = mapped_column(primary_key=True)
    digest_date: Mapped[datetime] = mapped_column(Date)
    version: Mapped[int] = mapped_column(Integer)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), default="published")
    daily_judgement: Mapped[str] = mapped_column(Text, default="")

    items: Mapped[list[DigestItem]] = relationship(back_populates="digest")
    github_projects: Mapped[list[DigestGitHubProject]] = relationship(back_populates="digest")

    __table_args__ = (UniqueConstraint("digest_date", "version"),)


class DigestItem(Base):
    __tablename__ = "digest_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    digest_id: Mapped[int] = mapped_column(ForeignKey("digests.id", ondelete="CASCADE"))
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"))
    position: Mapped[int] = mapped_column(Integer)
    core_summary: Mapped[str] = mapped_column(Text)
    importance: Mapped[str] = mapped_column(String(30))
    trend: Mapped[str] = mapped_column(String(120))
    topic_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    relevance: Mapped[float | None] = mapped_column(Float, nullable=True)

    digest: Mapped[Digest] = relationship(back_populates="items")
    article: Mapped[Article] = relationship(back_populates="digest_items")

    __table_args__ = (
        UniqueConstraint("digest_id", "position"),
        UniqueConstraint("digest_id", "article_id"),
    )


class DigestGitHubProject(Base):
    __tablename__ = "digest_github_projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    digest_id: Mapped[int] = mapped_column(ForeignKey("digests.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    full_name: Mapped[str] = mapped_column(String(300))
    recommendation: Mapped[str] = mapped_column(Text, default="")
    final_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    digest: Mapped[Digest] = relationship(back_populates="github_projects")

    __table_args__ = (UniqueConstraint("digest_id", "position"),)
