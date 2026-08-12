# app/config.py
"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_DOTENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _load_dotenv(path: Path | None = None) -> dict[str, str]:
    """Read a small dotenv file without mutating the process environment."""
    path = path or _DOTENV_PATH
    if not path.is_file():
        return {}

    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        name, separator, value = line.partition("=")
        if not separator or not name.isidentifier():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[name] = value
    return values


def _env(name: str, dotenv: dict[str, str]) -> str:
    """Explicit process environment wins over the project dotenv file."""
    if name in os.environ:
        return os.environ[name].strip()
    return dotenv.get(name, "").strip()


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
    feishu_app_id: str | None = None
    feishu_app_secret: str | None = None
    feishu_chat_id: str | None = None

    def __repr__(self) -> str:
        masked = self.llm_api_key[:7] + "***" if len(self.llm_api_key) > 7 else "***"
        masked_wecom = "***" if self.wecom_webhook_url else ""
        return (
            f"AppConfig(llm_api_key={masked!r}, llm_base_url={self.llm_base_url!r}, "
            f"llm_model={self.llm_model!r}, wecom_webhook_url={masked_wecom!r}, "
            f"tz={self.tz!r}, news_rss_urls={self.news_rss_urls!r}, "
            f"telegram_bot_token={'***' if self.telegram_bot_token else None!r}, "
            f"telegram_chat_id={'***' if self.telegram_chat_id else None!r}, "
            f"telegram_proxy={self.telegram_proxy!r}, "
            f"feishu_app_id={'***' if self.feishu_app_id else None!r}, "
            f"feishu_app_secret={'***' if self.feishu_app_secret else None!r}, "
            f"feishu_chat_id={'***' if self.feishu_chat_id else None!r})"
        )


def load_config() -> AppConfig:
    """Load configuration from environment variables.

    Raises:
        ValueError: If a required variable is missing or empty.
    """
    dotenv = _load_dotenv()
    required = {
        "LLM_API_KEY": _env("LLM_API_KEY", dotenv),
        "LLM_BASE_URL": _env("LLM_BASE_URL", dotenv),
        "LLM_MODEL": _env("LLM_MODEL", dotenv),
    }
    for name, value in required.items():
        if not value:
            raise ValueError(f"missing required environment variable: {name}")

    news_rss_urls_raw = _env("NEWS_RSS_URLS", dotenv)
    news_rss_urls = (
        [url.strip() for url in news_rss_urls_raw.split(",") if url.strip()]
        if news_rss_urls_raw
        else []
    )

    tz = _env("TZ", dotenv)
    telegram_bot_token = _env("TELEGRAM_BOT_TOKEN", dotenv) or None
    telegram_chat_id = _env("TELEGRAM_CHAT_ID", dotenv) or None
    telegram_proxy = _env("TELEGRAM_PROXY", dotenv) or None
    if telegram_bot_token and not telegram_chat_id:
        raise ValueError("missing required paired environment variable: TELEGRAM_CHAT_ID")
    if telegram_chat_id and not telegram_bot_token:
        raise ValueError("missing required paired environment variable: TELEGRAM_BOT_TOKEN")

    feishu_app_id = _env("FEISHU_APP_ID", dotenv) or None
    feishu_app_secret = _env("FEISHU_APP_SECRET", dotenv) or None
    feishu_chat_id = _env("FEISHU_CHAT_ID", dotenv) or None
    if feishu_app_id and not feishu_app_secret:
        raise ValueError("missing required paired environment variable: FEISHU_APP_SECRET")
    if feishu_app_secret and not feishu_app_id:
        raise ValueError("missing required paired environment variable: FEISHU_APP_ID")
    if feishu_chat_id and not (feishu_app_id and feishu_app_secret):
        raise ValueError("FEISHU_CHAT_ID requires FEISHU_APP_ID and FEISHU_APP_SECRET")

    return AppConfig(
        llm_api_key=required["LLM_API_KEY"],
        llm_base_url=required["LLM_BASE_URL"],
        llm_model=required["LLM_MODEL"],
        wecom_webhook_url=_env("WECOM_WEBHOOK_URL", dotenv),
        tz=tz if tz else "Asia/Shanghai",
        news_rss_urls=news_rss_urls,
        telegram_bot_token=telegram_bot_token,
        telegram_chat_id=telegram_chat_id,
        telegram_proxy=telegram_proxy,
        feishu_app_id=feishu_app_id,
        feishu_app_secret=feishu_app_secret,
        feishu_chat_id=feishu_chat_id,
    )
