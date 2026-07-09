"""GitHub 项目曝光历史存储。沿用 data/ github 目录，每天记录 push 过的项目。
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path


class GitHubExposureStore:
    def __init__(self, root_dir: Path | None = None):
        if root_dir is None:
            root_dir = Path(__file__).resolve().parent.parent.parent
        self.store_path = root_dir / "data" / "github" / "exposure.json"

    def load(self) -> dict[str, date]:
        """加载 {full_name: last_exposure_date}。"""
        if not self.store_path.exists():
            return {}
        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
            return {k: date.fromisoformat(v) for k, v in data.items()}
        except (OSError, json.JSONDecodeError, ValueError):
            return {}

    def record(self, full_names: list[str]) -> dict[str, date]:
        """记录本次曝光的项目，返回更新后的映射。"""
        current = self.load()
        today = date.today()
        for name in full_names:
            current[name] = today
        self._write(current)
        return current

    def _write(self, exposure: dict[str, date]) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {k: v.isoformat() for k, v in exposure.items()}
        tmp = self.store_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.store_path)
