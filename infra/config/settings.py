# infra/config/settings.py
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class CollectorSourceFlags:
    rss: bool = True
    huggingface: bool = True
    taptap: bool = True


@dataclass(frozen=True)
class Settings:
    fetch_count: int
    top_n: int
    collector_sources: CollectorSourceFlags
    rss_feeds: list[dict]
    keywords: dict[str, list[str]]
    wecom_webhook: str

    @classmethod
    def load(cls, config_path: Path) -> "Settings":
        if not config_path.exists():
            raise ValueError(f"config file not found: {config_path}")
        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        collectors = raw.get("collectors", {})
        source_flags = collectors.get("sources", {})
        webhook = os.getenv("PUSHER_WECOM_WEBHOOK") or raw.get("pusher", {}).get(
            "wecom_webhook", ""
        )
        return cls(
            fetch_count=collectors.get("fetch_count", 10),
            top_n=collectors.get("top_n", 5),
            collector_sources=CollectorSourceFlags(
                rss=source_flags.get("rss", True),
                huggingface=source_flags.get("huggingface", True),
                taptap=source_flags.get("taptap", True),
            ),
            rss_feeds=raw.get("rss_feeds", []),
            keywords=raw.get("keywords", {}),
            wecom_webhook=webhook,
        )

    def validate_for_run(self, dry_run: bool) -> None:
        if dry_run:
            return
        prefix = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key="
        if not self.wecom_webhook.startswith(prefix) or not self.wecom_webhook[len(prefix) :]:
            raise ValueError("invalid wecom webhook")
