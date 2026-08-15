"""发布库失败后的本地 outbox；独立于消息投递和已发布去重状态。"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from app.pipeline.candidate import CandidateItem


class PublicationRetryStore:
    def __init__(self, data_dir: Path):
        self._root = data_dir / "pending_publications"
        self._articles = self._root / "articles"
        self._digests = self._root / "digests"
        self._recovered_digests = self._root / "recovered_digests"

    def enqueue_articles(self, candidates: list[CandidateItem], feed_configuration: dict) -> None:
        if not candidates:
            return
        self._write(
            self._articles / f"{uuid.uuid4().hex}.json",
            {
                "kind": "articles",
                "candidates": [asdict(candidate) for candidate in candidates],
                "feed_configuration": feed_configuration,
            },
        )

    def enqueue_digest(self, *, date: str, period: str, payload: dict) -> bool:
        """保存首次失败的同日日报，避免覆盖已经投递的消息内容。"""
        if self.has_pending_digest(date):
            return False
        self._write(self._digests / f"{date}-{period}.json", {"kind": "digest", **payload})
        return True

    def replay_articles(self, publisher) -> None:
        for path in self._paths(self._articles):
            payload = self._read(path)
            candidates = [CandidateItem(**item) for item in payload["candidates"]]
            publisher.publish_candidates(candidates, payload["feed_configuration"])
            path.unlink()

    def replay_digests(self, publisher) -> None:
        for path in self._paths(self._digests):
            payload = self._read(path)
            publisher.publish_digest(
                digest_date=payload["digest_date"],
                published_at=datetime.fromisoformat(payload["published_at"]),
                headline_items=payload["headline_items"],
                selected=[CandidateItem(**item) for item in payload["selected"]],
                daily_judgement=payload["daily_judgement"],
                github_projects=payload["github_projects"],
            )
            self.mark_digest_published(payload["digest_date"])
            path.unlink()

    def pending_article_count(self) -> int:
        return len(self._paths(self._articles))

    def pending_digest_count(self) -> int:
        return len(self._paths(self._digests))

    def has_pending_digest(self, digest_date: str) -> bool:
        for path in self._paths(self._digests):
            if self._read(path).get("digest_date") == digest_date:
                return True
        return False

    def has_recovered_digest(self, digest_date: str) -> bool:
        return (self._recovered_digests / f"{digest_date}.json").is_file()

    def mark_digest_published(self, digest_date: str) -> None:
        self._write(
            self._recovered_digests / f"{digest_date}.json",
            {"digest_date": digest_date},
        )

    @staticmethod
    def _paths(directory: Path) -> list[Path]:
        return sorted(directory.glob("*.json")) if directory.exists() else []

    @staticmethod
    def _read(path: Path) -> dict:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"publication retry payload is not an object: {path.name}")
        PublicationRetryStore._validate_secret_free(payload)
        return payload

    @staticmethod
    def _write(path: Path, payload: dict) -> None:
        PublicationRetryStore._validate_secret_free(payload)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temp_path.replace(path)

    @staticmethod
    def _validate_secret_free(payload: dict) -> None:
        secret_markers = (
            "token",
            "secret",
            "password",
            "authorization",
            "api_key",
            "apikey",
            "credential",
            "access_key",
            "private_key",
            "chat_id",
        )
        secret_query_keys = {
            "access_token",
            "access_key",
            "api_key",
            "apikey",
            "authorization",
            "credential",
            "credentials",
            "key",
            "password",
            "private_key",
            "secret",
            "signature",
            "token",
        }

        def walk(value: object) -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    if any(marker in str(key).lower() for marker in secret_markers):
                        raise ValueError("publication retry payload contains secret field")
                    walk(child)
                return
            if isinstance(value, list):
                for child in value:
                    walk(child)
                return
            if not isinstance(value, str):
                return
            parsed = urlsplit(value)
            if not parsed.scheme or not parsed.netloc:
                return
            if parsed.username is not None or parsed.password is not None:
                raise ValueError("publication retry payload contains secret URL credentials")
            for key, _ in parse_qsl(parsed.query, keep_blank_values=True):
                if key.lower() in secret_query_keys:
                    raise ValueError("publication retry payload contains secret URL query")

        walk(payload)
