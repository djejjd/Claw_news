# app/config.py
"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AppConfig:
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    wecom_webhook_url: str
    tz: str
    news_rss_urls: list[str]


def load_config() -> AppConfig:
    """Load configuration from environment variables.

    Raises:
        ValueError: If a required variable is missing or empty.
    """
    required = {
        "LLM_API_KEY": os.getenv("LLM_API_KEY", "").strip(),
        "LLM_BASE_URL": os.getenv("LLM_BASE_URL", "").strip(),
        "LLM_MODEL": os.getenv("LLM_MODEL", "").strip(),
        "WECOM_WEBHOOK_URL": os.getenv("WECOM_WEBHOOK_URL", "").strip(),
    }
    for name, value in required.items():
        if not value:
            raise ValueError(f"missing required environment variable: {name}")

    news_rss_urls_raw = os.getenv("NEWS_RSS_URLS", "").strip()
    news_rss_urls = (
        [url.strip() for url in news_rss_urls_raw.split(",") if url.strip()]
        if news_rss_urls_raw
        else []
    )

    tz = os.getenv("TZ", "").strip()

    return AppConfig(
        llm_api_key=required["LLM_API_KEY"],
        llm_base_url=required["LLM_BASE_URL"],
        llm_model=required["LLM_MODEL"],
        wecom_webhook_url=required["WECOM_WEBHOOK_URL"],
        tz=tz if tz else "Asia/Shanghai",
        news_rss_urls=news_rss_urls,
    )
