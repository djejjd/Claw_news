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
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    telegram_proxy: str | None = None

    def __repr__(self) -> str:
        masked = self.llm_api_key[:7] + "***" if len(self.llm_api_key) > 7 else "***"
        return (
            f"AppConfig(llm_api_key={masked!r}, llm_base_url={self.llm_base_url!r}, "
            f"llm_model={self.llm_model!r}, wecom_webhook_url={self.wecom_webhook_url!r}, "
            f"tz={self.tz!r}, news_rss_urls={self.news_rss_urls!r}, "
            f"telegram_bot_token={'***' if self.telegram_bot_token else None!r}, "
            f"telegram_chat_id={'***' if self.telegram_chat_id else None!r}, "
            f"telegram_proxy={self.telegram_proxy!r})"
        )


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
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or None
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip() or None
    telegram_proxy = os.getenv("TELEGRAM_PROXY", "").strip() or None
    if telegram_bot_token and not telegram_chat_id:
        raise ValueError("missing required paired environment variable: TELEGRAM_CHAT_ID")
    if telegram_chat_id and not telegram_bot_token:
        raise ValueError("missing required paired environment variable: TELEGRAM_BOT_TOKEN")

    return AppConfig(
        llm_api_key=required["LLM_API_KEY"],
        llm_base_url=required["LLM_BASE_URL"],
        llm_model=required["LLM_MODEL"],
        wecom_webhook_url=required["WECOM_WEBHOOK_URL"],
        tz=tz if tz else "Asia/Shanghai",
        news_rss_urls=news_rss_urls,
        telegram_bot_token=telegram_bot_token,
        telegram_chat_id=telegram_chat_id,
        telegram_proxy=telegram_proxy,
    )
