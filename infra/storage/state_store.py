from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.tools.summary_result import DigestPayload


class StateStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.pushed_urls_path = data_dir / "pushed_urls.json"
        self.published_keys_path = data_dir / "published_keys.json"

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

    # ------------------------------------------------------------------
    # Phase 7: digest-shaped persistence
    # ------------------------------------------------------------------

    def write_digest(self, digest: DigestPayload) -> None:
        """写入 digest-shaped JSON：data/{digest.date}/ai_digest.json."""
        day_dir = self.data_dir / digest.date
        digest_path = day_dir / "ai_digest.json"
        payload = asdict(digest)
        self._atomic_write_json(digest_path, payload)

    def load_published_keys(self) -> set[str]:
        """加载已发布的 canonical_keys."""
        if not self.published_keys_path.exists():
            return set()
        try:
            with open(self.published_keys_path, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except (OSError, json.JSONDecodeError):
            return set()

    def merge_published_keys(self, keys: list[str]) -> set[str]:
        """合并 published_keys 到持久化存储."""
        current = self.load_published_keys()
        merged = current | set(keys)
        self._atomic_write_json(self.published_keys_path, sorted(merged))
        return merged

    # ------------------------------------------------------------------

    def _atomic_write_json(self, path: Path, payload) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        tmp_path.replace(path)
