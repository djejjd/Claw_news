from pathlib import Path

from app.storage.source_metrics_store import SourceMetricsStore


def test_append_run_metric_writes_jsonl_record(tmp_path: Path):
    store = SourceMetricsStore(root_dir=tmp_path)
    store.append_run_metric(
        {
            "source": "qbitai",
            "run_id": "run123",
            "run_started_at": "2026-05-19T10:00:00",
            "raw_fetched_count": 10,
            "deduped_new_count": 4,
            "accepted_count": 3,
            "selected_count": 1,
            "rejected_duplicate_count": 6,
            "rejected_quality_count": 1,
            "duration_ms": 1280,
            "status": "ok",
        }
    )

    rows = store.load_day_metrics("2026-05-19")
    assert len(rows) == 1
    assert rows[0]["source"] == "qbitai"
    assert rows[0]["accepted_count"] == 3


def test_aggregate_recent_metrics_returns_effective_new_and_selection_rates(tmp_path: Path):
    store = SourceMetricsStore(root_dir=tmp_path)
    for payload in [
        {
            "source": "qbitai",
            "run_id": "r1",
            "run_started_at": "2026-05-19T10:00:00",
            "raw_fetched_count": 10,
            "deduped_new_count": 5,
            "accepted_count": 4,
            "selected_count": 2,
            "rejected_duplicate_count": 5,
            "rejected_quality_count": 1,
            "duration_ms": 1000,
            "status": "ok",
        },
        {
            "source": "qbitai",
            "run_id": "r2",
            "run_started_at": "2026-05-19T10:30:00",
            "raw_fetched_count": 8,
            "deduped_new_count": 2,
            "accepted_count": 2,
            "selected_count": 0,
            "rejected_duplicate_count": 6,
            "rejected_quality_count": 0,
            "duration_ms": 950,
            "status": "ok",
        },
    ]:
        store.append_run_metric(payload)

    summary = store.aggregate_recent(source="qbitai", limit=10)
    assert summary["raw_fetched_count"] == 18
    assert summary["accepted_count"] == 6
    assert summary["effective_new_rate"] == 6 / 18
    assert summary["selection_rate"] == 2 / 6


def test_aggregate_recent_sorts_by_run_started_at_before_windowing(tmp_path: Path):
    store = SourceMetricsStore(root_dir=tmp_path)
    store.append_run_metric(
        {
            "source": "qbitai",
            "run_id": "late",
            "run_started_at": "2026-05-19T10:30:00",
            "raw_fetched_count": 10,
            "deduped_new_count": 4,
            "accepted_count": 3,
            "selected_count": 1,
            "rejected_duplicate_count": 6,
            "rejected_quality_count": 1,
            "duration_ms": 1200,
            "status": "ok",
        }
    )
    store.append_run_metric(
        {
            "source": "qbitai",
            "run_id": "early",
            "run_started_at": "2026-05-19T09:00:00",
            "raw_fetched_count": 8,
            "deduped_new_count": 2,
            "accepted_count": 1,
            "selected_count": 0,
            "rejected_duplicate_count": 7,
            "rejected_quality_count": 1,
            "duration_ms": 900,
            "status": "ok",
        }
    )

    summary = store.aggregate_recent(source="qbitai", limit=1)
    assert summary["raw_fetched_count"] == 10
    assert summary["accepted_count"] == 3
    assert summary["effective_new_rate"] == 3 / 10
    assert summary["selection_rate"] == 1 / 3


def test_write_selected_counts_updates_latest_metric_and_selection_rate(tmp_path: Path):
    store = SourceMetricsStore(root_dir=tmp_path)
    store.append_run_metric(
        {
            "source": "qbitai",
            "run_id": "late",
            "run_started_at": "2026-05-19T10:30:00",
            "raw_fetched_count": 10,
            "deduped_new_count": 4,
            "accepted_count": 4,
            "selected_count": 0,
            "rejected_duplicate_count": 6,
            "rejected_quality_count": 0,
            "duration_ms": 1200,
            "status": "ok",
        }
    )
    store.append_run_metric(
        {
            "source": "qbitai",
            "run_id": "early",
            "run_started_at": "2026-05-19T09:00:00",
            "raw_fetched_count": 8,
            "deduped_new_count": 2,
            "accepted_count": 2,
            "selected_count": 0,
            "rejected_duplicate_count": 6,
            "rejected_quality_count": 0,
            "duration_ms": 900,
            "status": "ok",
        }
    )
    store.append_run_metric(
        {
            "source": "huggingface",
            "run_id": "hf",
            "run_started_at": "2026-05-19T09:15:00",
            "raw_fetched_count": 5,
            "deduped_new_count": 3,
            "accepted_count": 3,
            "selected_count": 0,
            "rejected_duplicate_count": 2,
            "rejected_quality_count": 0,
            "duration_ms": 800,
            "status": "ok",
        }
    )

    updated = store.write_selected_counts({"qbitai": 3, "huggingface": 1})

    assert updated == 2

    rows = store.load_day_metrics("2026-05-19")
    assert [row["selected_count"] for row in rows if row["source"] == "qbitai"] == [3, 0]
    assert [row["selected_count"] for row in rows if row["source"] == "huggingface"] == [1]

    summary = store.aggregate_recent(source="qbitai", limit=10)
    assert summary["selected_count"] == 3
    assert summary["selection_rate"] == 3 / 6
