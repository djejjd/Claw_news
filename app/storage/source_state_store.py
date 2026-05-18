from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


class SourceStateStore:
    def __init__(self, root_dir: Optional[Path] = None):
        if root_dir is None:
            root_dir = Path(__file__).resolve().parent.parent.parent
        self.state_dir = root_dir / "data" / "source_state"

    def load_state(self, source: str, default_fetch_count: int) -> dict:
        path = self._path_for(source)
        default_state = self._default_state(source, default_fetch_count)
        if not path.exists():
            return default_state

        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return default_state

        if not isinstance(loaded, dict):
            return default_state

        state = {
            **default_state,
            **{
                key: loaded[key]
                for key in (
                    "fetch_count",
                    "min_fetch_count",
                    "max_fetch_count",
                    "cooldown_remaining",
                    "last_adjusted_at",
                )
                if key in loaded
            },
        }
        state["source"] = source
        return state

    def save_state(self, source: str, payload: dict) -> Path:
        path = self._path_for(source)
        path.parent.mkdir(parents=True, exist_ok=True)

        state = {"source": source}
        for field in (
            "fetch_count",
            "min_fetch_count",
            "max_fetch_count",
            "cooldown_remaining",
            "last_adjusted_at",
        ):
            if field in payload:
                state[field] = payload[field]

        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return path

    def _path_for(self, source: str) -> Path:
        return self.state_dir / f"{source}.json"

    @staticmethod
    def _default_state(source: str, default_fetch_count: int) -> dict:
        return {
            "source": source,
            "fetch_count": default_fetch_count,
            "min_fetch_count": default_fetch_count,
            "max_fetch_count": default_fetch_count,
            "cooldown_remaining": 0,
            "last_adjusted_at": None,
        }
