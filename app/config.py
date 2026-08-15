# app/config.py
"""Application configuration loaded from environment variables."""

from __future__ import annotations

import math
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


def _bool_env(name: str, dotenv: dict[str, str], default: bool = False) -> bool:
    raw = _env(name, dotenv).lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes"}:
        return True
    if raw in {"0", "false", "no"}:
        return False
    raise ValueError(f"{name} must be 0 or 1")


@dataclass(frozen=True)
class AppConfig:
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    wecom_webhook_url: str
    tz: str
    news_rss_urls: list[str]
    source_failure_degraded_threshold: int = 3
    selection_diversity_penalty_profile: str = "linear"
    topic_cluster_enabled: bool = False
    topic_cluster_similarity_threshold: float = 0.7
    topic_cluster_max_rounds: int = 10
    llm_relevance_enabled: bool = False
    llm_relevance_threshold: float = 0.5
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
    threshold_raw = _env("SOURCE_FAILURE_DEGRADED_THRESHOLD", dotenv)
    try:
        source_failure_degraded_threshold = int(threshold_raw) if threshold_raw else 3
    except ValueError as exc:
        raise ValueError("SOURCE_FAILURE_DEGRADED_THRESHOLD must be a positive integer") from exc
    if source_failure_degraded_threshold <= 0:
        raise ValueError("SOURCE_FAILURE_DEGRADED_THRESHOLD must be a positive integer")
    diversity_profile = _env("SELECTION_DIVERSITY_PENALTY_PROFILE", dotenv).lower() or "linear"
    if diversity_profile not in {"linear", "exponential"}:
        raise ValueError("SELECTION_DIVERSITY_PENALTY_PROFILE must be linear or exponential")
    topic_cluster_enabled = _bool_env("TOPIC_CLUSTER_ENABLED", dotenv)
    cluster_threshold_raw = _env("TOPIC_CLUSTER_SIMILARITY_THRESHOLD", dotenv)
    try:
        topic_cluster_similarity_threshold = float(cluster_threshold_raw or "0.7")
    except ValueError as exc:
        raise ValueError("TOPIC_CLUSTER_SIMILARITY_THRESHOLD must be in (0, 1]") from exc
    if not 0 < topic_cluster_similarity_threshold <= 1:
        raise ValueError("TOPIC_CLUSTER_SIMILARITY_THRESHOLD must be in (0, 1]")
    rounds_raw = _env("TOPIC_CLUSTER_MAX_ROUNDS", dotenv)
    try:
        topic_cluster_max_rounds = int(rounds_raw or "10")
    except ValueError as exc:
        raise ValueError("TOPIC_CLUSTER_MAX_ROUNDS must be positive") from exc
    if topic_cluster_max_rounds <= 0:
        raise ValueError("TOPIC_CLUSTER_MAX_ROUNDS must be positive")
    llm_relevance_enabled = _bool_env("LLM_RELEVANCE_ENABLED", dotenv)
    relevance_threshold_raw = _env("LLM_RELEVANCE_THRESHOLD", dotenv)
    try:
        llm_relevance_threshold = float(relevance_threshold_raw or "0.5")
    except ValueError as exc:
        raise ValueError("LLM_RELEVANCE_THRESHOLD must be in (0, 1]") from exc
    if not math.isfinite(llm_relevance_threshold) or not 0 < llm_relevance_threshold <= 1:
        raise ValueError("LLM_RELEVANCE_THRESHOLD must be in (0, 1]")
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
        source_failure_degraded_threshold=source_failure_degraded_threshold,
        selection_diversity_penalty_profile=diversity_profile,
        topic_cluster_enabled=topic_cluster_enabled,
        topic_cluster_similarity_threshold=topic_cluster_similarity_threshold,
        topic_cluster_max_rounds=topic_cluster_max_rounds,
        llm_relevance_enabled=llm_relevance_enabled,
        llm_relevance_threshold=llm_relevance_threshold,
        telegram_bot_token=telegram_bot_token,
        telegram_chat_id=telegram_chat_id,
        telegram_proxy=telegram_proxy,
        feishu_app_id=feishu_app_id,
        feishu_app_secret=feishu_app_secret,
        feishu_chat_id=feishu_chat_id,
    )
