"""Atomic, secret-free persistence for incomplete multi-channel deliveries."""

from __future__ import annotations

import json
from pathlib import Path


class PendingDeliveryCorruptError(RuntimeError):
    """Raised when a pending-delivery record cannot be safely recovered."""


class PendingDeliveryStore:
    def __init__(self, data_dir: Path):
        self._directory = data_dir / "pending_deliveries"

    def load(self, date: str, period: str) -> dict | None:
        path = self._path(date, period)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PendingDeliveryCorruptError(
                f"pending delivery cannot be read: {path.name}"
            ) from exc
        if not isinstance(payload, dict):
            raise PendingDeliveryCorruptError(f"pending delivery is not an object: {path.name}")
        self._validate_secret_free(payload)
        return payload

    def save(self, date: str, period: str, payload: dict) -> None:
        self._validate_secret_free(payload)
        path = self._path(date, period)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(path)

    def delete(self, date: str, period: str) -> None:
        path = self._path(date, period)
        if path.exists():
            path.unlink()

    def _path(self, date: str, period: str) -> Path:
        return self._directory / f"{date}-{period}.json"

    @staticmethod
    def _validate_secret_free(payload: dict) -> None:
        def walk(value: object) -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    if "token" in key.lower() or "chat_id" in key.lower():
                        raise ValueError("pending delivery payload contains secret field")
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(payload)
