# tests/test_app_config.py

import pytest

from app.config import load_config


class TestLoadConfigMissingRequired:
    """Step 1: missing a required env var must raise ValueError."""

    def test_missing_llm_api_key(self, monkeypatch):
        monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
        monkeypatch.setenv(
            "WECOM_WEBHOOK_URL", "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test"
        )
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        with pytest.raises(ValueError, match="LLM_API_KEY"):
            load_config()

    def test_missing_llm_base_url(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
        monkeypatch.setenv(
            "WECOM_WEBHOOK_URL", "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test"
        )
        monkeypatch.delenv("LLM_BASE_URL", raising=False)
        with pytest.raises(ValueError, match="LLM_BASE_URL"):
            load_config()

    def test_missing_llm_model(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setenv(
            "WECOM_WEBHOOK_URL", "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test"
        )
        monkeypatch.delenv("LLM_MODEL", raising=False)
        with pytest.raises(ValueError, match="LLM_MODEL"):
            load_config()

    def test_missing_wecom_webhook_url(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
        monkeypatch.delenv("WECOM_WEBHOOK_URL", raising=False)
        with pytest.raises(ValueError, match="WECOM_WEBHOOK_URL"):
            load_config()

    def test_empty_llm_api_key(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
        monkeypatch.setenv(
            "WECOM_WEBHOOK_URL", "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test"
        )
        with pytest.raises(ValueError, match="LLM_API_KEY"):
            load_config()


class TestDefaults:
    def test_tz_defaults_to_asia_shanghai(self, monkeypatch):
        """TZ must default to Asia/Shanghai when not set."""
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
        monkeypatch.setenv(
            "WECOM_WEBHOOK_URL", "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test"
        )
        monkeypatch.delenv("TZ", raising=False)
        config = load_config()
        assert config.tz == "Asia/Shanghai"

    def test_news_rss_urls_defaults_to_empty_list(self, monkeypatch):
        """NEWS_RSS_URLS defaults to empty list when not set."""
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
        monkeypatch.setenv(
            "WECOM_WEBHOOK_URL", "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test"
        )
        monkeypatch.delenv("NEWS_RSS_URLS", raising=False)
        config = load_config()
        assert config.news_rss_urls == []


class TestNewsRssUrlsParsing:
    def test_parses_single_url(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
        monkeypatch.setenv(
            "WECOM_WEBHOOK_URL", "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test"
        )
        monkeypatch.setenv("NEWS_RSS_URLS", "https://example.com/feed.xml")
        config = load_config()
        assert config.news_rss_urls == ["https://example.com/feed.xml"]

    def test_parses_comma_separated_urls(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
        monkeypatch.setenv(
            "WECOM_WEBHOOK_URL", "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test"
        )
        monkeypatch.setenv(
            "NEWS_RSS_URLS",
            "https://example.com/ai.xml,https://example.com/game.xml",
        )
        config = load_config()
        assert config.news_rss_urls == [
            "https://example.com/ai.xml",
            "https://example.com/game.xml",
        ]

    def test_strips_whitespace_around_urls(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
        monkeypatch.setenv(
            "WECOM_WEBHOOK_URL", "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test"
        )
        monkeypatch.setenv(
            "NEWS_RSS_URLS",
            " https://example.com/ai.xml , https://example.com/game.xml ",
        )
        config = load_config()
        assert config.news_rss_urls == [
            "https://example.com/ai.xml",
            "https://example.com/game.xml",
        ]

    def test_empty_env_var_gives_empty_list(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
        monkeypatch.setenv(
            "WECOM_WEBHOOK_URL", "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test"
        )
        monkeypatch.setenv("NEWS_RSS_URLS", "")
        config = load_config()
        assert config.news_rss_urls == []


class TestHappyPath:
    def test_all_fields_set(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
        monkeypatch.setenv(
            "WECOM_WEBHOOK_URL", "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test"
        )
        monkeypatch.setenv("TZ", "Asia/Tokyo")
        monkeypatch.setenv("NEWS_RSS_URLS", "https://example.com/feed.xml")
        config = load_config()
        assert config.llm_api_key == "sk-test"
        assert config.llm_base_url == "https://api.openai.com/v1"
        assert config.llm_model == "gpt-4.1-mini"
        assert (
            config.wecom_webhook_url == "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test"
        )
        assert config.tz == "Asia/Tokyo"
        assert config.news_rss_urls == ["https://example.com/feed.xml"]


class TestTelegramConfiguration:
    def test_telegram_is_disabled_when_both_fields_are_empty(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
        monkeypatch.setenv("WECOM_WEBHOOK_URL", "https://example.test/wecom")
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

        config = load_config()

        assert config.telegram_bot_token is None
        assert config.telegram_chat_id is None

    def test_telegram_requires_token_and_chat_id_together(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
        monkeypatch.setenv("WECOM_WEBHOOK_URL", "https://example.test/wecom")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:secret-token")
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

        with pytest.raises(ValueError, match="TELEGRAM_CHAT_ID"):
            load_config()

    def test_telegram_values_are_loaded_and_masked_in_repr(self, monkeypatch):
        token = "123:secret-token"
        chat_id = "987654321"
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
        monkeypatch.setenv("WECOM_WEBHOOK_URL", "https://example.test/wecom")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", token)
        monkeypatch.setenv("TELEGRAM_CHAT_ID", chat_id)

        config = load_config()

        assert config.telegram_bot_token == token
        assert config.telegram_chat_id == chat_id
        assert token not in repr(config)
        assert chat_id not in repr(config)
