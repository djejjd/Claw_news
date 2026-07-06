# tests/test_state_store_digest.py
import json
from pathlib import Path

from app.tools.summary_result import DigestPayload
from infra.storage.state_store import StateStore

# ------------------------------------------------------------------
# write_digest
# ------------------------------------------------------------------


def test_write_digest_creates_file(tmp_path: Path):
    store = StateStore(data_dir=tmp_path)
    digest = DigestPayload(
        date="2026-05-18",
        period="morning",
        published_at="2026-05-18T08:00:00",
        trigger_mode="cron",
        headline_items=[{"title": "Test", "url": "https://example.com"}],
        daily_judgement="All good",
    )

    store.write_digest(digest)

    digest_path = tmp_path / "2026-05-18" / "ai_digest.json"
    assert digest_path.exists()


def test_write_digest_contains_all_required_fields(tmp_path: Path):
    store = StateStore(data_dir=tmp_path)
    digest = DigestPayload(
        date="2026-05-18",
        period="evening",
        published_at="2026-05-18T20:00:00",
        trigger_mode="manual",
        headline_items=[
            {"title": "Article 1", "url": "https://a.com/1"},
            {"title": "Article 2", "url": "https://a.com/2"},
        ],
        daily_judgement="Busy day",
        source_failures=["source_a timed out"],
        published_urls=["https://a.com/1", "https://a.com/2"],
        published_keys=["key_001", "key_002"],
    )

    store.write_digest(digest)

    digest_path = tmp_path / "2026-05-18" / "ai_digest.json"
    payload = json.loads(digest_path.read_text(encoding="utf-8"))

    assert payload["date"] == "2026-05-18"
    assert payload["period"] == "evening"
    assert payload["published_at"] == "2026-05-18T20:00:00"
    assert payload["trigger_mode"] == "manual"
    assert len(payload["headline_items"]) == 2
    assert payload["headline_items"][0]["title"] == "Article 1"
    assert payload["daily_judgement"] == "Busy day"
    assert payload["source_failures"] == ["source_a timed out"]
    assert payload["published_urls"] == ["https://a.com/1", "https://a.com/2"]
    assert payload["published_keys"] == ["key_001", "key_002"]


def test_write_digest_overwrites_existing_file(tmp_path: Path):
    store = StateStore(data_dir=tmp_path)

    digest_v1 = DigestPayload(
        date="2026-05-18",
        period="morning",
        published_at="2026-05-18T08:00:00",
        trigger_mode="cron",
        headline_items=[{"title": "First", "url": "https://a.com/1"}],
        daily_judgement="Morning judgement",
    )
    store.write_digest(digest_v1)

    digest_v2 = DigestPayload(
        date="2026-05-18",
        period="morning",
        published_at="2026-05-18T08:30:00",
        trigger_mode="re-trigger",
        headline_items=[{"title": "Second", "url": "https://b.com/2"}],
        daily_judgement="Updated judgement",
    )
    store.write_digest(digest_v2)

    digest_path = tmp_path / "2026-05-18" / "ai_digest.json"
    payload = json.loads(digest_path.read_text(encoding="utf-8"))

    assert payload["published_at"] == "2026-05-18T08:30:00"
    assert payload["trigger_mode"] == "re-trigger"
    assert payload["headline_items"][0]["title"] == "Second"
    assert payload["daily_judgement"] == "Updated judgement"


def test_write_digest_default_empty_lists(tmp_path: Path):
    """DigestPayload fields with default_factory=list should serialize as []."""
    store = StateStore(data_dir=tmp_path)
    digest = DigestPayload(
        date="2026-05-18",
        period="morning",
        published_at="2026-05-18T08:00:00",
        trigger_mode="cron",
    )

    store.write_digest(digest)

    digest_path = tmp_path / "2026-05-18" / "ai_digest.json"
    payload = json.loads(digest_path.read_text(encoding="utf-8"))

    assert payload["headline_items"] == []
    assert payload["daily_judgement"] == ""
    assert payload["source_failures"] == []
    assert payload["published_urls"] == []
    assert payload["published_keys"] == []


# ------------------------------------------------------------------
# load_published_keys / merge_published_keys
# ------------------------------------------------------------------


def test_load_published_keys_returns_empty_when_missing(tmp_path: Path):
    store = StateStore(data_dir=tmp_path)
    assert store.load_published_keys() == set()


def test_merge_published_keys_adds_new_keys(tmp_path: Path):
    store = StateStore(data_dir=tmp_path)
    merged = store.merge_published_keys(["key_a", "key_b"])
    assert merged == {"key_a", "key_b"}


def test_merge_published_keys_merges_with_existing(tmp_path: Path):
    store = StateStore(data_dir=tmp_path)
    store.merge_published_keys(["key_a", "key_b"])
    merged = store.merge_published_keys(["key_b", "key_c"])
    assert merged == {"key_a", "key_b", "key_c"}


def test_load_published_keys_reads_merged_keys(tmp_path: Path):
    store = StateStore(data_dir=tmp_path)
    store.merge_published_keys(["key_1", "key_2"])
    keys = store.load_published_keys()
    assert keys == {"key_1", "key_2"}


def test_merge_and_load_roundtrip(tmp_path: Path):
    store = StateStore(data_dir=tmp_path)

    merged = store.merge_published_keys(["alpha"])
    assert merged == {"alpha"}
    assert store.load_published_keys() == {"alpha"}

    merged = store.merge_published_keys(["beta", "gamma"])
    assert merged == {"alpha", "beta", "gamma"}
    assert store.load_published_keys() == {"alpha", "beta", "gamma"}


# ------------------------------------------------------------------
# Atomic writes — no .tmp residue
# ------------------------------------------------------------------


def test_write_digest_atomic_no_tmp_residue(tmp_path: Path):
    store = StateStore(data_dir=tmp_path)
    digest = DigestPayload(
        date="2026-05-18",
        period="morning",
        published_at="2026-05-18T08:00:00",
        trigger_mode="cron",
        headline_items=[{"title": "Atomic", "url": "https://example.com"}],
    )

    store.write_digest(digest)

    day_dir = tmp_path / "2026-05-18"
    tmp_files = list(day_dir.glob("*.tmp"))
    assert len(tmp_files) == 0, f"Expected no .tmp files, found: {tmp_files}"


def test_merge_published_keys_atomic_no_tmp_residue(tmp_path: Path):
    store = StateStore(data_dir=tmp_path)
    store.merge_published_keys(["key_x", "key_y"])

    tmp_files = list(tmp_path.glob("*.tmp"))
    assert len(tmp_files) == 0, f"Expected no .tmp files, found: {tmp_files}"


# ------------------------------------------------------------------
# Coexistence with existing methods
# ------------------------------------------------------------------


def test_published_keys_independent_from_pushed_urls(tmp_path: Path):
    """published_keys and pushed_urls are stored in separate files."""
    store = StateStore(data_dir=tmp_path)

    store.merge_pushed_urls({"https://a.com/1"})
    store.merge_published_keys(["key_1"])

    assert store.load_pushed_urls() == {"https://a.com/1"}
    assert store.load_published_keys() == {"key_1"}

    # Verify separate files on disk
    assert (tmp_path / "pushed_urls.json").exists()
    assert (tmp_path / "published_keys.json").exists()
