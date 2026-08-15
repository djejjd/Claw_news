from dataclasses import asdict
from datetime import datetime, timezone

import pytest

from app.pipeline.candidate import CandidateItem
from app.publication.retry_store import PublicationRetryStore


def _candidate() -> CandidateItem:
    return CandidateItem(
        title="Retry article",
        url="https://example.test/retry",
        summary="retry summary",
        source="retry_source",
        category="ai",
        canonical_key="example.test/retry",
        fetched_at="2026-08-15T09:00:00+00:00",
    )


class _Publisher:
    def __init__(self):
        self.article_batches = []
        self.digests = []

    def publish_candidates(self, candidates, feed_configuration):
        self.article_batches.append((candidates, feed_configuration))

    def publish_digest(self, **payload):
        self.digests.append(payload)


def test_article_batch_survives_until_a_successful_replay(tmp_path):
    retries = PublicationRetryStore(tmp_path)
    candidate = _candidate()
    retries.enqueue_articles([candidate], {"feeds": {"ai": []}})

    publisher = _Publisher()
    retries.replay_articles(publisher)

    assert publisher.article_batches[0][0][0] == candidate
    assert retries.pending_article_count() == 0


def test_digest_survives_until_a_successful_replay(tmp_path):
    retries = PublicationRetryStore(tmp_path)
    candidate = _candidate()
    retries.enqueue_digest(
        date="2026-08-15",
        period="morning",
        payload={
            "digest_date": "2026-08-15",
            "published_at": datetime(2026, 8, 15, 1, tzinfo=timezone.utc).isoformat(),
            "headline_items": [
                {
                    "url": candidate.url,
                    "core_summary": "summary",
                    "importance": "high",
                    "trend": "up",
                }
            ],
            "selected": [asdict(candidate)],
            "daily_judgement": "judgement",
            "github_projects": [],
        },
    )

    publisher = _Publisher()
    retries.replay_digests(publisher)

    assert publisher.digests[0]["digest_date"] == "2026-08-15"
    assert publisher.digests[0]["selected"][0] == candidate
    assert retries.pending_digest_count() == 0
    assert retries.has_recovered_digest("2026-08-15") is True


def test_first_pending_digest_is_not_overwritten_by_a_later_run(tmp_path):
    retries = PublicationRetryStore(tmp_path)
    candidate = _candidate()
    first_payload = {
        "digest_date": "2026-08-15",
        "published_at": datetime(2026, 8, 15, 1, tzinfo=timezone.utc).isoformat(),
        "headline_items": [],
        "selected": [asdict(candidate)],
        "daily_judgement": "first digest",
        "github_projects": [],
    }
    later_payload = {**first_payload, "daily_judgement": "later digest"}

    retries.enqueue_digest(date="2026-08-15", period="morning", payload=first_payload)
    retries.enqueue_digest(date="2026-08-15", period="morning", payload=later_payload)

    publisher = _Publisher()
    retries.replay_digests(publisher)

    assert publisher.digests[0]["daily_judgement"] == "first digest"


def test_failed_article_replay_keeps_the_pending_batch(tmp_path):
    retries = PublicationRetryStore(tmp_path)
    retries.enqueue_articles([_candidate()], {"feeds": {}})

    class FailingPublisher:
        def publish_candidates(self, candidates, feed_configuration):
            raise RuntimeError("database unavailable")

    try:
        retries.replay_articles(FailingPublisher())
    except RuntimeError:
        pass

    assert retries.pending_article_count() == 1


def test_article_outbox_rejects_feed_urls_with_embedded_credentials(tmp_path):
    retries = PublicationRetryStore(tmp_path)

    with pytest.raises(ValueError, match="secret"):
        retries.enqueue_articles(
            [_candidate()],
            {"feeds": {"ai": [{"source": "private", "url": "https://token@example.test/feed"}]}},
        )

    assert not (tmp_path / "pending_publications").exists()


@pytest.mark.parametrize("query_key", ["signature", "access_key", "private_key"])
def test_article_outbox_rejects_sensitive_feed_query_without_rejecting_canonical_key(
    tmp_path, query_key
):
    retries = PublicationRetryStore(tmp_path)

    with pytest.raises(ValueError, match="secret"):
        retries.enqueue_articles(
            [_candidate()],
            {
                "feeds": {
                    "ai": [
                        {
                            "source": "private",
                            "url": f"https://example.test/feed?{query_key}=secret-value",
                        }
                    ]
                }
            },
        )

    assert not (tmp_path / "pending_publications").exists()


def test_article_outbox_replay_rejects_an_existing_secret_payload(tmp_path):
    retries = PublicationRetryStore(tmp_path)
    pending_path = tmp_path / "pending_publications" / "articles" / "legacy.json"
    pending_path.parent.mkdir(parents=True)
    pending_path.write_text(
        '{"kind":"articles","candidates":[],"feed_configuration":{"token":"secret"}}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="secret"):
        retries.replay_articles(_Publisher())
