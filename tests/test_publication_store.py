from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.exc import OperationalError

from app.pipeline.candidate import CandidateItem
from app.publication.models import Article, Digest
from app.publication.public_api import PublicationUnavailableError
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


def test_public_articles_only_return_whitelisted_published_content(store):
    store.publish_articles(
        [
            _candidate(canonical_key="published", title="Published"),
            _candidate(canonical_key="hidden", title="Hidden"),
            _candidate(canonical_key="expired", title="Expired"),
        ]
    )
    with store._sessions.begin() as session:
        session.query(Article).filter_by(canonical_key="hidden").update({"visibility": "hidden"})
        session.query(Article).filter_by(canonical_key="expired").update({"visibility": "expired"})

    page = store.list_public_articles(
        start_date=date(2026, 8, 15),
        end_date=date(2026, 8, 15),
        tz="UTC",
        page=1,
        page_size=20,
    )

    assert [article.title for article in page.items] == ["Published"]
    payload = page.items[0].model_dump()
    assert payload == {
        "id": payload["id"],
        "title": "Published",
        "original_url": "https://example.test/news?id=1",
        "category": "digital",
        "topic": "hardware_chip",
        "summary": "First source summary",
        "published_at": "2026-08-15T08:00:00+00:00",
        "fetched_at": "2026-08-15T09:00:00+00:00",
        "source": {
            "name": "example_source",
            "display_name": "example_source",
            "site_url": None,
        },
    }
    assert "topic_confidence" not in payload
    assert "canonical_key" not in payload
    assert "visibility" not in payload


def test_cleanup_expired_publication_preserves_retained_digest_references_and_is_idempotent(store):
    store.publish_articles(
        [
            _candidate(
                canonical_key="old-unreferenced",
                title="Old unreferenced",
                fetched_at="2026-08-05T12:00:00+00:00",
            ),
            _candidate(
                canonical_key="old-retained",
                title="Old retained",
                fetched_at="2026-08-05T12:00:00+00:00",
            ),
            _candidate(
                canonical_key="current", title="Current", fetched_at="2026-08-16T12:00:00+00:00"
            ),
        ]
    )
    store.publish_digest(
        digest_date="2026-08-05",
        version=1,
        published_at=datetime(2026, 8, 5, tzinfo=timezone.utc),
        daily_judgement="old",
        items=[
            {
                "canonical_key": "old-unreferenced",
                "position": 1,
                "core_summary": "old",
                "importance": "low",
                "trend": "flat",
            }
        ],
        github_projects=[{"full_name": "old/project", "recommendation": "old"}],
    )
    store.publish_digest(
        digest_date="2026-08-16",
        version=1,
        published_at=datetime(2026, 8, 16, tzinfo=timezone.utc),
        daily_judgement="current",
        items=[
            {
                "canonical_key": "old-retained",
                "position": 1,
                "core_summary": "kept",
                "importance": "high",
                "trend": "up",
            }
        ],
        github_projects=[],
    )

    result = store.cleanup_expired_publication(local_today=date(2026, 8, 16), tz="UTC")

    assert result.marked_expired_article_ids
    assert result.deleted_digest_items == 1
    assert result.deleted_github_projects == 1
    assert result.deleted_digests == 1
    assert result.deleted_article_ids == result.marked_expired_article_ids
    with pytest.raises(LookupError, match="old-unreferenced"):
        store.get_article("old-unreferenced")
    assert store.get_article("old-retained").visibility == "published"
    assert store.count_digests() == 1
    assert (
        store.cleanup_expired_publication(local_today=date(2026, 8, 16), tz="UTC").deleted_digests
        == 0
    )


def test_cleanup_expired_publication_uses_exact_ten_day_boundary(store):
    store.publish_articles(
        [
            _candidate(
                canonical_key="eleventh-day",
                title="Eleventh day",
                fetched_at="2026-08-06T12:00:00+00:00",
            ),
            _candidate(
                canonical_key="tenth-day",
                title="Tenth day",
                fetched_at="2026-08-07T12:00:00+00:00",
            ),
        ]
    )

    first = store.cleanup_expired_publication(local_today=date(2026, 8, 16), tz="UTC")

    assert len(first.marked_expired_article_ids) == 1
    with pytest.raises(LookupError, match="eleventh-day"):
        store.get_article("eleventh-day")
    assert store.get_article("tenth-day").visibility == "published"

    second = store.cleanup_expired_publication(local_today=date(2026, 8, 17), tz="UTC")

    assert len(second.marked_expired_article_ids) == 1
    with pytest.raises(LookupError, match="tenth-day"):
        store.get_article("tenth-day")


def test_public_article_query_uses_local_day_boundary_and_stable_id_order(store):
    shanghai = ZoneInfo("Asia/Shanghai")
    local_day = date(2026, 8, 16)
    start = datetime(2026, 8, 16, 0, 0, tzinfo=shanghai)
    store.publish_articles(
        [
            _candidate(
                canonical_key="before-day",
                title="Before day",
                fetched_at=(start - timedelta(microseconds=1)).astimezone(timezone.utc).isoformat(),
            ),
            _candidate(
                canonical_key="same-time-a",
                title="Same time A",
                published_at=None,
                fetched_at=(start + timedelta(hours=2)).astimezone(timezone.utc).isoformat(),
            ),
            _candidate(
                canonical_key="same-time-b",
                title="Same time B",
                published_at=None,
                fetched_at=(start + timedelta(hours=2)).astimezone(timezone.utc).isoformat(),
            ),
            _candidate(
                canonical_key="after-day",
                title="After day",
                fetched_at=(start + timedelta(days=1)).astimezone(timezone.utc).isoformat(),
            ),
        ]
    )

    page = store.list_public_articles(
        start_date=local_day,
        end_date=local_day,
        tz="Asia/Shanghai",
        page=1,
        page_size=20,
    )

    assert [article.title for article in page.items] == ["Same time A", "Same time B"]


def test_public_article_read_does_not_write_or_update_records(store):
    store.publish_articles([_candidate()])
    article = store.get_article("example.test/news")
    original_fetched_at = article.fetched_at

    store.list_public_articles(
        start_date=date(2026, 8, 15),
        end_date=date(2026, 8, 15),
        tz="UTC",
        page=1,
        page_size=20,
    )

    assert store.count_articles() == 1
    assert store.get_article("example.test/news").fetched_at == original_fetched_at


def test_public_sources_only_include_windowed_published_articles(store):
    store.publish_articles(
        [
            _candidate(canonical_key="visible-source", source="Visible source"),
            _candidate(canonical_key="hidden-source", source="Hidden source"),
            _candidate(
                canonical_key="old-source",
                source="Old source",
                fetched_at="2026-08-01T09:00:00+00:00",
            ),
        ]
    )
    with store._sessions.begin() as session:
        session.query(Article).filter_by(canonical_key="hidden-source").update(
            {"visibility": "hidden"}
        )

    sources = store.list_public_sources(
        start_date=date(2026, 8, 15),
        end_date=date(2026, 8, 15),
        tz="UTC",
    )

    assert [source.model_dump() for source in sources] == [
        {"name": "Visible source", "display_name": "Visible source", "site_url": None}
    ]


def test_public_digest_hides_internal_fields_and_non_published_article(store):
    store.publish_articles([_candidate()])
    store.publish_digest(
        digest_date="2026-08-15",
        version=1,
        published_at=datetime(2026, 8, 15, 9, tzinfo=timezone.utc),
        daily_judgement="Daily judgement",
        items=[
            {
                "canonical_key": "example.test/news",
                "position": 1,
                "core_summary": "Core summary",
                "importance": "high",
                "trend": "up",
                "topic_label": "AI",
                "relevance": 0.9,
            }
        ],
        github_projects=[
            {"full_name": "owner/project", "recommendation": "Recommended", "final_score": 9.9}
        ],
    )

    digest = store.get_public_digest(date(2026, 8, 15), local_today=date(2026, 8, 16))

    assert digest is not None
    payload = digest.model_dump()
    assert payload["items"][0]["article"]["title"] == "First title"
    assert "relevance" not in payload["items"][0]
    assert "final_score" not in payload["github_projects"][0]
    assert "status" not in payload
    with store._sessions.begin() as session:
        session.query(Article).filter_by(canonical_key="example.test/news").update(
            {"visibility": "hidden"}
        )
    assert store.get_public_digest(date(2026, 8, 15), local_today=date(2026, 8, 16)) is None
    with store._sessions.begin() as session:
        session.query(Article).filter_by(canonical_key="example.test/news").update(
            {"visibility": "expired"}
        )
    assert store.get_public_digest(date(2026, 8, 15), local_today=date(2026, 8, 16)) is None
    with store._sessions.begin() as session:
        session.query(Article).filter_by(canonical_key="example.test/news").update(
            {"visibility": "published"}
        )
        session.query(Digest).filter_by(digest_date=date(2026, 8, 15)).update({"status": "draft"})
    assert store.get_public_digest(date(2026, 8, 15), local_today=date(2026, 8, 16)) is None


def test_public_digest_limits_results_to_the_local_ten_day_window(store):
    store.publish_articles([_candidate()])
    for digest_day in (date(2026, 8, 6), date(2026, 8, 7)):
        store.publish_digest(
            digest_date=digest_day.isoformat(),
            version=1,
            published_at=datetime(2026, 8, 16, 9, tzinfo=timezone.utc),
            daily_judgement="Daily judgement",
            items=[
                {
                    "canonical_key": "example.test/news",
                    "position": 1,
                    "core_summary": "Core summary",
                    "importance": "high",
                    "trend": "up",
                }
            ],
            github_projects=[],
        )

    assert store.get_public_digest(date(2026, 8, 6), local_today=date(2026, 8, 16)) is None
    assert store.get_public_digest(date(2026, 8, 7), local_today=date(2026, 8, 16)) is not None


def test_public_read_converts_database_details_to_domain_error(store, monkeypatch):
    def unavailable_sessions():
        raise OperationalError("SELECT 1", {}, RuntimeError("postgresql://private-host/news"))

    monkeypatch.setattr(store, "_sessions", unavailable_sessions)

    with pytest.raises(PublicationUnavailableError) as error:
        store.list_public_articles(
            start_date=date(2026, 8, 15),
            end_date=date(2026, 8, 15),
            tz="UTC",
            page=1,
            page_size=20,
        )

    assert str(error.value) == "publication_unavailable"


@pytest.mark.parametrize("query", ["sources", "digest"])
def test_other_public_reads_convert_database_details_to_domain_error(store, monkeypatch, query):
    def unavailable_sessions():
        raise OperationalError("SELECT 1", {}, RuntimeError("postgresql://private-host/news"))

    monkeypatch.setattr(store, "_sessions", unavailable_sessions)

    with pytest.raises(PublicationUnavailableError) as error:
        if query == "sources":
            store.list_public_sources(
                start_date=date(2026, 8, 15),
                end_date=date(2026, 8, 15),
                tz="UTC",
            )
        else:
            store.get_public_digest(date(2026, 8, 15), local_today=date(2026, 8, 16))

    assert str(error.value) == "publication_unavailable"
