# tests/test_state_store.py
import json
from pathlib import Path

from infra.storage.state_store import StateStore


def test_load_pushed_urls_returns_empty_when_missing(tmp_path: Path):
    store = StateStore(tmp_path)
    assert store.load_pushed_urls() == set()


def test_merge_pushed_urls_deduplicates(tmp_path: Path):
    store = StateStore(tmp_path)
    merged = store.merge_pushed_urls({"https://a.com/1", "https://a.com/2"})
    merged = store.merge_pushed_urls({"https://a.com/2", "https://a.com/3"})
    assert merged == {"https://a.com/1", "https://a.com/2", "https://a.com/3"}


def test_write_daily_digest_category_builds_partial_record(tmp_path: Path):
    store = StateStore(tmp_path)
    store.write_daily_digest_category(
        period="morning",
        category="ai",
        items=[{"title": "AI 1", "url": "https://a.com/1"}],
    )
    store.write_daily_digest_category(
        period="morning",
        category="game",
        items=[{"title": "Game 1", "url": "https://g.com/1"}],
    )
    digest_files = list((tmp_path / store.today_str()).glob("morning.json"))
    assert len(digest_files) == 1
    payload = json.loads(digest_files[0].read_text(encoding="utf-8"))
    assert payload["ai"][0]["title"] == "AI 1"
    assert payload["game"][0]["title"] == "Game 1"
    assert "device" not in payload
