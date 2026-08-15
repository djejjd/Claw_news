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


def test_selection_eligible_counts_replace_adaptive_rate_without_rewriting_legacy_rows(
    tmp_path: Path,
):
    store = SourceMetricsStore(root_dir=tmp_path)
    store.append_run_metric(
        {
            "source": "qbitai",
            "run_id": "legacy",
            "run_started_at": "2026-05-19T09:00:00",
            "raw_fetched_count": 8,
            "deduped_new_count": 2,
            "accepted_count": 2,
            "selected_count": 1,
            "rejected_duplicate_count": 6,
            "rejected_quality_count": 0,
            "duration_ms": 900,
            "status": "ok",
        }
    )
    store.append_run_metric(
        {
            "source": "qbitai",
            "run_id": "current",
            "run_started_at": "2026-05-19T10:00:00",
            "raw_fetched_count": 10,
            "deduped_new_count": 5,
            "accepted_count": 4,
            "selected_count": 0,
            "rejected_duplicate_count": 5,
            "rejected_quality_count": 1,
            "duration_ms": 900,
            "status": "ok",
        }
    )

    updated = store.write_selection_eligible_counts({"qbitai": 3})

    rows = store.load_day_metrics("2026-05-19")
    assert updated == 1
    assert "selection_eligible_count" not in rows[0]
    assert rows[1]["selection_eligible_count"] == 3
    assert store.aggregate_recent("qbitai")["selection_rate"] == 4 / 6


def test_selection_eligible_counts_update_only_the_requested_ingest_run(tmp_path: Path):
    """同一来源多轮 ingest 时，L2 初选数不能回写到较新的另一轮。"""
    store = SourceMetricsStore(root_dir=tmp_path)
    for run_id, run_started_at in (
        ("target", "2026-05-19T09:00:00"),
        ("later", "2026-05-19T10:00:00"),
    ):
        store.append_run_metric(
            {
                "source": "qbitai",
                "run_id": run_id,
                "run_started_at": run_started_at,
                "raw_fetched_count": 10,
                "deduped_new_count": 4,
                "accepted_count": 4,
                "selected_count": 0,
                "rejected_duplicate_count": 6,
                "rejected_quality_count": 0,
                "duration_ms": 1000,
                "status": "ok",
            }
        )

    assert (
        store.write_selection_eligible_counts({"qbitai": 3}, run_started_at="2026-05-19T09:00:00")
        == 1
    )

    rows = store.load_day_metrics("2026-05-19")
    assert rows[0]["selection_eligible_count"] == 3
    assert "selection_eligible_count" not in rows[1]
