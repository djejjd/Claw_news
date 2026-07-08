from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


class IngestStatusStore:
    def __init__(self, root_dir: Optional[Path] = None):
        if root_dir is None:
            root_dir = Path(__file__).resolve().parent.parent.parent
        self.path = root_dir / "data" / "ingestion_status.json"

    def write_status(self, payload: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def load_status(self) -> dict:
        if not self.path.exists():
            return {
                "last_ingest_at": None,
                "last_item_count": 0,
                "successful_sources": [],
                "failed_sources": [],
                "skipped_sources": [],
            }
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {
                "last_ingest_at": None,
                "last_item_count": 0,
                "successful_sources": [],
                "failed_sources": [],
                "skipped_sources": [],
            }
