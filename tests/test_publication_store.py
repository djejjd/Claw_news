from datetime import datetime, timezone

import pytest

from app.pipeline.candidate import CandidateItem
from app.publication.store import PublicationStore


def _candidate(**overrides) -> CandidateItem:
    values = {
        "title": "First title",
        "url": "https://example.test/news?id=1",
        "summary": "First source summary",
        "source": "example_source",
        "category": "digital",
        "published_at": "2026-08-15T08:00:00+00:00",
        "fetched_at": "2026-08-15T09:00:00+00:00",
        "canonical_key": "example.test/news",
        "topic": "hardware_chip",
        "topic_confidence": 0.8,
    }
    values.update(overrides)
    return CandidateItem(**values)


@pytest.fixture
def store(tmp_path):
    instance = PublicationStore(f"sqlite:///{tmp_path / 'publication.db'}")
    instance.create_schema()
    return instance


def test_article_upsert_uses_canonical_key_and_newer_published_at(store):
    first = _candidate()
    newer = _candidate(
        title="Updated title",
        summary="Updated source summary",
        published_at="2026-08-15T10:00:00+00:00",
        fetched_at="2026-08-15T10:01:00+00:00",
    )

    assert store.publish_articles([first]) == 1
    assert store.publish_articles([newer]) == 1

    article = store.get_article("example.test/news")
    assert article.title == "Updated title"
    assert article.source_summary == "Updated source summary"
    assert store.count_articles() == 1


def test_healthcheck_executes_a_database_probe(store):
    store.healthcheck()


def test_digest_exists_uses_natural_day_and_version(store):
    assert store.digest_exists("2026-08-15") is False
    store.publish_digest(
        digest_date="2026-08-15",
        version=1,
        published_at=datetime(2026, 8, 15, 9, tzinfo=timezone.utc),
        daily_judgement="Daily judgement",
        items=[],
        github_projects=[],
    )

    assert store.digest_exists("2026-08-15") is True
    assert store.digest_exists("2026-08-15", version=2) is False


def test_article_upsert_keeps_newer_existing_article_when_input_is_stale(store):
    store.publish_articles([_candidate(published_at="2026-08-15T10:00:00+00:00")])
    store.publish_articles(
        [_candidate(title="Stale title", published_at="2026-08-15T08:00:00+00:00")]
    )

    assert store.get_article("example.test/news").title == "First title"


def test_source_default_category_does_not_override_article_category(store):
    store.publish_sources(
        [
            {
                "name": "example_source",
                "display_name": "Example Source",
                "default_category": "tool",
                "site_url": "https://example.test",
                "feeds": [{"url": "https://example.test/rss", "collector_type": "rss"}],
            }
        ]
    )
    store.publish_articles([_candidate(category="digital")])

    assert store.get_source("example_source").default_category == "tool"
    assert store.get_article("example.test/news").category == "digital"
    assert store.count_source_feeds("example_source") == 1


def test_digest_write_is_atomic_when_a_digest_item_references_unknown_article(store):
    store.publish_articles([_candidate()])

    with pytest.raises(ValueError, match="unknown article"):
        store.publish_digest(
            digest_date="2026-08-15",
            version=1,
            published_at=datetime(2026, 8, 15, 9, tzinfo=timezone.utc),
            daily_judgement="Daily judgement",
            items=[
                {
                    "canonical_key": "example.test/news",
                    "position": 1,
                    "core_summary": "Summary",
                    "importance": "high",
                    "trend": "up",
                    "relevance": 0.9,
                },
                {
                    "canonical_key": "missing.test/news",
                    "position": 2,
                    "core_summary": "Missing",
                    "importance": "low",
                    "trend": "flat",
                    "relevance": 0.1,
                },
            ],
            github_projects=[],
        )

    assert store.count_digests() == 0
    assert store.count_digest_items() == 0
