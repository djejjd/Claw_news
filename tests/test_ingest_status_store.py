from pathlib import Path

from app.storage.ingest_status_store import IngestStatusStore


def test_write_and_load_status(tmp_path: Path):
    store = IngestStatusStore(root_dir=tmp_path)
    payload = {
        "last_ingest_at": "2026-05-18T08:00:00",
        "last_item_count": 3,
        "successful_sources": ["rss"],
        "failed_sources": ["huggingface: timeout"],
        "skipped_sources": ["github: optional"],
    }

    store.write_status(payload)

    assert store.load_status() == payload


def test_load_status_defaults_include_skipped_sources(tmp_path: Path):
    store = IngestStatusStore(root_dir=tmp_path)

    assert store.load_status() == {
        "last_ingest_at": None,
        "last_item_count": 0,
        "successful_sources": [],
        "failed_sources": [],
        "skipped_sources": [],
    }
