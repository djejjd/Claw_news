from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional


class SourceMetricsStore:
    def __init__(self, root_dir: Optional[Path] = None):
        if root_dir is None:
            root_dir = Path(__file__).resolve().parent.parent.parent
        self.metrics_dir = root_dir / "data" / "source_metrics"

    def append_run_metric(self, payload: dict) -> Path:
        started_at = datetime.fromisoformat(payload["run_started_at"])
        day_dir = self.metrics_dir / started_at.date().isoformat()
        day_dir.mkdir(parents=True, exist_ok=True)

        path = day_dir / "metrics.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return path

    def load_day_metrics(self, day: str) -> list[dict]:
        path = self.metrics_dir / day / "metrics.jsonl"
        if not path.exists():
            return []

        rows: list[dict] = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
        return rows

    def write_selected_counts(self, selected_counts: dict[str, int]) -> int:
        updated = 0
        for source, selected_count in selected_counts.items():
            if self.write_selected_count(source, selected_count):
                updated += 1
        return updated

    def write_selected_count(self, source: str, selected_count: int) -> bool:
        latest = self._find_latest_metric_row(source)
        if latest is None:
            return False

        path, rows, row_index = latest
        rows[row_index]["selected_count"] = selected_count

        tmp_path = path.with_name(path.name + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        tmp_path.replace(path)
        return True

    def aggregate_recent(self, source: str, limit: int = 24) -> dict:
        rows = self._load_all_for_source(source)
        rows.sort(key=lambda row: row["run_started_at"])
        recent = rows[-limit:] if limit else []

        raw_fetched_count = sum(row.get("raw_fetched_count", 0) for row in recent)
        accepted_count = sum(row.get("accepted_count", 0) for row in recent)
        selected_count = sum(row.get("selected_count", 0) for row in recent)

        return {
            "source": source,
            "runs": len(recent),
            "raw_fetched_count": raw_fetched_count,
            "accepted_count": accepted_count,
            "selected_count": selected_count,
            "effective_new_rate": (accepted_count / raw_fetched_count) if raw_fetched_count else 0.0,
            "selection_rate": (selected_count / accepted_count) if accepted_count else 0.0,
        }

    def _load_all_for_source(self, source: str) -> list[dict]:
        if not self.metrics_dir.exists():
            return []

        rows: list[dict] = []
        for day_dir in sorted(self.metrics_dir.iterdir()):
            if not day_dir.is_dir():
                continue
            path = day_dir / "metrics.jsonl"
            if not path.exists():
                continue
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    payload = json.loads(line)
                    if payload.get("source") == source:
                        rows.append(payload)
        return rows

    def _find_latest_metric_row(self, source: str) -> tuple[Path, list[dict], int] | None:
        if not self.metrics_dir.exists():
            return None

        latest_path: Path | None = None
        latest_rows: list[dict] | None = None
        latest_index: int | None = None
        latest_started_at: datetime | None = None

        for day_dir in sorted(self.metrics_dir.iterdir()):
            if not day_dir.is_dir():
                continue
            path = day_dir / "metrics.jsonl"
            if not path.exists():
                continue

            rows: list[dict] = []
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rows.append(json.loads(line))

            for idx, row in enumerate(rows):
                if row.get("source") != source:
                    continue
                run_started_at = row.get("run_started_at", "")
                try:
                    started_at = datetime.fromisoformat(run_started_at)
                except ValueError:
                    continue
                if latest_started_at is None or started_at > latest_started_at:
                    latest_path = path
                    latest_rows = rows
                    latest_index = idx
                    latest_started_at = started_at

        if latest_path is None or latest_rows is None or latest_index is None:
            return None
        return latest_path, latest_rows, latest_index
