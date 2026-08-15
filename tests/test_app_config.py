# tests/test_app_config.py

import pytest

import app.config as config_module
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

    def test_wecom_webhook_optional(self, monkeypatch):
        """WECOM_WEBHOOK_URL 缺省时 wecom_webhook_url 为空字符串，不抛错。"""
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
        monkeypatch.delenv("WECOM_WEBHOOK_URL", raising=False)
        config = load_config()
        assert config.wecom_webhook_url == ""

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

    def test_source_failure_degraded_threshold_defaults_to_three(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
        monkeypatch.delenv("SOURCE_FAILURE_DEGRADED_THRESHOLD", raising=False)

        assert load_config().source_failure_degraded_threshold == 3

    def test_source_failure_degraded_threshold_must_be_positive_integer(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
        monkeypatch.setenv("SOURCE_FAILURE_DEGRADED_THRESHOLD", "0")

        with pytest.raises(ValueError, match="SOURCE_FAILURE_DEGRADED_THRESHOLD"):
            load_config()

    def test_selection_diversity_profile_defaults_to_linear(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
        monkeypatch.delenv("SELECTION_DIVERSITY_PENALTY_PROFILE", raising=False)

        assert load_config().selection_diversity_penalty_profile == "linear"

    def test_selection_diversity_profile_rejects_unknown_value(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
        monkeypatch.setenv("SELECTION_DIVERSITY_PENALTY_PROFILE", "stepped")

        with pytest.raises(ValueError, match="SELECTION_DIVERSITY_PENALTY_PROFILE"):
            load_config()

    def test_topic_cluster_defaults_are_disabled(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
        for name in (
            "TOPIC_CLUSTER_ENABLED",
            "TOPIC_CLUSTER_SIMILARITY_THRESHOLD",
            "TOPIC_CLUSTER_MAX_ROUNDS",
        ):
            monkeypatch.delenv(name, raising=False)

        config = load_config()

        assert config.topic_cluster_enabled is False
        assert config.topic_cluster_similarity_threshold == 0.7
        assert config.topic_cluster_max_rounds == 10

    @pytest.mark.parametrize(
        ("name", "value", "message"),
        [
            ("TOPIC_CLUSTER_ENABLED", "enabled", "must be 0 or 1"),
            ("TOPIC_CLUSTER_SIMILARITY_THRESHOLD", "0", "must be in"),
            ("TOPIC_CLUSTER_SIMILARITY_THRESHOLD", "1.1", "must be in"),
            ("TOPIC_CLUSTER_MAX_ROUNDS", "0", "must be positive"),
        ],
    )
    def test_topic_cluster_invalid_config_is_rejected(self, monkeypatch, name, value, message):
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
        monkeypatch.setenv(name, value)

        with pytest.raises(ValueError, match=message):
            load_config()

    @pytest.mark.parametrize(
        ("name", "value", "message"),
        [
            ("LLM_RELEVANCE_ENABLED", "enabled", "must be 0 or 1"),
            ("LLM_RELEVANCE_THRESHOLD", "0", "must be in"),
            ("LLM_RELEVANCE_THRESHOLD", "1.1", "must be in"),
        ],
    )
    def test_llm_relevance_invalid_config_is_rejected(self, monkeypatch, name, value, message):
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
        monkeypatch.setenv(name, value)

        with pytest.raises(ValueError, match=message):
            load_config()

    def test_llm_relevance_defaults_are_disabled(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
        monkeypatch.delenv("LLM_RELEVANCE_ENABLED", raising=False)
        monkeypatch.delenv("LLM_RELEVANCE_THRESHOLD", raising=False)

        config = load_config()

        assert config.llm_relevance_enabled is False
        assert config.llm_relevance_threshold == 0.5


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
    def test_loads_dotenv_when_process_environment_is_empty(self, monkeypatch, tmp_path):
        dotenv_path = tmp_path / ".env"
        dotenv_path.write_text(
            "LLM_API_KEY=sk-from-dotenv\n"
            "LLM_BASE_URL=https://dotenv.example/v1\n"
            "LLM_MODEL=dotenv-model\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(config_module, "_DOTENV_PATH", dotenv_path)
        for name in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
            monkeypatch.delenv(name, raising=False)

        config = load_config()

        assert config.llm_api_key == "sk-from-dotenv"
        assert config.llm_base_url == "https://dotenv.example/v1"
        assert config.llm_model == "dotenv-model"

    def test_process_environment_overrides_dotenv(self, monkeypatch, tmp_path):
        dotenv_path = tmp_path / ".env"
        dotenv_path.write_text(
            "LLM_API_KEY=sk-from-dotenv\n"
            "LLM_BASE_URL=https://dotenv.example/v1\n"
            "LLM_MODEL=dotenv-model\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(config_module, "_DOTENV_PATH", dotenv_path)
        monkeypatch.setenv("LLM_API_KEY", "sk-from-environment")
        monkeypatch.delenv("LLM_BASE_URL", raising=False)
        monkeypatch.delenv("LLM_MODEL", raising=False)

        config = load_config()

        assert config.llm_api_key == "sk-from-environment"
        assert config.llm_base_url == "https://dotenv.example/v1"
        assert config.llm_model == "dotenv-model"

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

    def test_wecom_webhook_url_is_masked_in_repr(self, monkeypatch):
        """wecom webhook 含 key= 查询参数，repr 中必须掩码不泄露凭证。"""
        secret = "secret-key-123"
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
        monkeypatch.setenv(
            "WECOM_WEBHOOK_URL", f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={secret}"
        )
        config = load_config()
        assert config.wecom_webhook_url == (
            "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=secret-key-123"
        )
        assert f"key={secret}" not in repr(config)
        assert secret not in repr(config)
        assert "wecom_webhook_url='***'" in repr(config)


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


class TestFeishuConfig:
    def test_feishu_defaults_none(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
        config = load_config()
        assert config.feishu_app_id is None
        assert config.feishu_app_secret is None
        assert config.feishu_chat_id is None

    def test_feishu_partial_missing_raises(self, monkeypatch):
        """只配 app_id 不配 app_secret 时报错（与 telegram 配对校验一致）。"""
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
        monkeypatch.setenv("FEISHU_APP_ID", "cli_test")
        with pytest.raises(ValueError, match="FEISHU_APP_SECRET"):
            load_config()

    def test_feishu_full_config(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
        monkeypatch.setenv("FEISHU_APP_ID", "cli_test")
        monkeypatch.setenv("FEISHU_APP_SECRET", "secret_test")
        monkeypatch.setenv("FEISHU_CHAT_ID", "oc_test")
        config = load_config()
        assert config.feishu_app_id == "cli_test"
        assert config.feishu_app_secret == "secret_test"
        assert config.feishu_chat_id == "oc_test"
