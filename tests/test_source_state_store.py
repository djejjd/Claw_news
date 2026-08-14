from pathlib import Path

from app.storage.source_state_store import SourceStateStore


def test_load_state_returns_default_when_missing(tmp_path: Path):
    store = SourceStateStore(root_dir=tmp_path)

    state = store.load_state("qbitai", default_fetch_count=10)

    assert state["source"] == "qbitai"
    assert state["fetch_count"] == 10
    assert state["min_fetch_count"] == 10
    assert state["max_fetch_count"] == 10
    assert state["cooldown_remaining"] == 0
    assert state["last_adjusted_at"] is None
    assert state["consecutive_failure_count"] == 0
    assert state["last_success_at"] is None
    assert state["last_failure_at"] is None
    assert state["last_error"] is None


def test_load_state_returns_default_when_json_is_not_object(tmp_path: Path):
    store = SourceStateStore(root_dir=tmp_path)
    path = tmp_path / "data" / "source_state" / "qbitai.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[]", encoding="utf-8")

    state = store.load_state("qbitai", default_fetch_count=10)

    assert state["source"] == "qbitai"
    assert state["fetch_count"] == 10
    assert state["min_fetch_count"] == 10
    assert state["max_fetch_count"] == 10
    assert state["cooldown_remaining"] == 0
    assert state["last_adjusted_at"] is None


def test_load_state_returns_default_when_json_is_broken(tmp_path: Path):
    store = SourceStateStore(root_dir=tmp_path)
    path = tmp_path / "data" / "source_state" / "qbitai.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{", encoding="utf-8")

    state = store.load_state("qbitai", default_fetch_count=10)

    assert state["source"] == "qbitai"
    assert state["fetch_count"] == 10
    assert state["min_fetch_count"] == 10
    assert state["max_fetch_count"] == 10
    assert state["cooldown_remaining"] == 0
    assert state["last_adjusted_at"] is None


def test_save_state_then_load_state_reads_updated_fetch_count(tmp_path: Path):
    store = SourceStateStore(root_dir=tmp_path)

    store.save_state(
        "qbitai",
        {
            "source": "qbitai",
            "fetch_count": 14,
        },
    )

    state = store.load_state("qbitai", default_fetch_count=10)

    assert state["source"] == "qbitai"
    assert state["fetch_count"] == 14
    assert state["min_fetch_count"] == 10
    assert state["max_fetch_count"] == 10
    assert state["cooldown_remaining"] == 0
    assert state["last_adjusted_at"] is None


def test_load_state_fills_missing_fields_from_existing_file(tmp_path: Path):
    store = SourceStateStore(root_dir=tmp_path)
    path = tmp_path / "data" / "source_state" / "qbitai.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '{"source":"payload-source","fetch_count":7,"unexpected":"value"}',
        encoding="utf-8",
    )

    state = store.load_state("qbitai", default_fetch_count=10)

    assert state["source"] == "qbitai"
    assert state["fetch_count"] == 7
    assert state["min_fetch_count"] == 10
    assert state["max_fetch_count"] == 10
    assert state["cooldown_remaining"] == 0
    assert state["last_adjusted_at"] is None
    assert "unexpected" not in state


def test_save_state_then_load_state_preserves_known_fields_only(tmp_path: Path):
    store = SourceStateStore(root_dir=tmp_path)

    store.save_state(
        "qbitai",
        {
            "source": "payload-source",
            "fetch_count": 14,
            "min_fetch_count": 11,
            "max_fetch_count": 20,
            "cooldown_remaining": 2,
            "last_adjusted_at": "2026-05-19T10:00:00",
            "consecutive_failure_count": 2,
            "last_success_at": "2026-05-19T09:00:00",
            "last_failure_at": "2026-05-19T10:00:00",
            "last_error": "timeout",
            "unexpected": "value",
        },
    )

    state = store.load_state("qbitai", default_fetch_count=10)

    assert state["source"] == "qbitai"
    assert state["fetch_count"] == 14
    assert state["min_fetch_count"] == 11
    assert state["max_fetch_count"] == 20
    assert state["cooldown_remaining"] == 2
    assert state["last_adjusted_at"] == "2026-05-19T10:00:00"
    assert state["consecutive_failure_count"] == 2
    assert state["last_success_at"] == "2026-05-19T09:00:00"
    assert state["last_failure_at"] == "2026-05-19T10:00:00"
    assert state["last_error"] == "timeout"
    assert "unexpected" not in state


def test_save_state_writes_only_white_listed_fields_to_disk(tmp_path: Path):
    store = SourceStateStore(root_dir=tmp_path)

    path = store.save_state(
        "qbitai",
        {
            "source": "payload-source",
            "fetch_count": 14,
            "min_fetch_count": 11,
            "max_fetch_count": 20,
            "cooldown_remaining": 2,
            "last_adjusted_at": "2026-05-19T10:00:00",
            "unexpected": "value",
        },
    )

    assert path.read_text(encoding="utf-8") == (
        "{\n"
        '  "source": "qbitai",\n'
        '  "fetch_count": 14,\n'
        '  "min_fetch_count": 11,\n'
        '  "max_fetch_count": 20,\n'
        '  "cooldown_remaining": 2,\n'
        '  "last_adjusted_at": "2026-05-19T10:00:00"\n'
        "}"
    )
