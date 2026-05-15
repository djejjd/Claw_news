from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path


class StateStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.pushed_urls_path = data_dir / "pushed_urls.json"

    def today_str(self) -> str:
        return date.today().isoformat()

    def load_pushed_urls(self) -> set[str]:
        if not self.pushed_urls_path.exists():
            return set()
        try:
            with open(self.pushed_urls_path, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except (OSError, json.JSONDecodeError):
            return set()

    def merge_pushed_urls(self, urls: set[str]) -> set[str]:
        current = self.load_pushed_urls()
        merged = current | urls
        self._atomic_write_json(self.pushed_urls_path, sorted(merged))
        return merged

    def write_daily_digest_category(self, period: str, category: str, items: list[dict]) -> None:
        day_dir = self.data_dir / self.today_str()
        day_dir.mkdir(parents=True, exist_ok=True)
        digest_path = day_dir / f"{period}.json"

        if digest_path.exists():
            with open(digest_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        else:
            payload = {
                "period": period,
                "date": self.today_str(),
                "pushed_at": datetime.now().isoformat(),
            }

        payload[category] = items
        self._atomic_write_json(digest_path, payload)

    def _atomic_write_json(self, path: Path, payload) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        tmp_path.replace(path)
