from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Optional

from collectors.github import GitHubRepoItem


class GitHubStore:
    def __init__(self, root_dir: Optional[Path] = None):
        if root_dir is None:
            root_dir = Path(__file__).resolve().parent.parent.parent
        self.github_dir = root_dir / "data" / "github"

    def write_snapshot(self, items: list[GitHubRepoItem], date_str: str | None = None) -> Path:
        target_date = date_str or date.today().isoformat()
        day_dir = self.github_dir / target_date
        day_dir.mkdir(parents=True, exist_ok=True)
        path = day_dir / "repos.json"
        path.write_text(json.dumps([asdict(item) for item in items], ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def load_latest_snapshot(self) -> list[GitHubRepoItem]:
        if not self.github_dir.exists():
            return []
        dated_dirs = sorted([d for d in self.github_dir.iterdir() if d.is_dir()], reverse=True)
        for day_dir in dated_dirs:
            path = day_dir / "repos.json"
            if not path.exists():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                return [GitHubRepoItem(**item) for item in payload]
            except (OSError, json.JSONDecodeError, TypeError):
                continue
        return []
