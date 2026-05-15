# tests/test_settings.py
from pathlib import Path

import pytest

from infra.config.settings import Settings


def test_settings_loads_yaml_defaults(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
collectors:
  fetch_count: 10
  top_n: 5
  sources:
    rss: true
    huggingface: true
    taptap: false
rss_feeds:
  - url: "https://example.com/feed"
    category: "ai"
    source: "demo"
keywords:
  ai: ["AI"]
pusher:
  wecom_webhook: ""
""".strip(),
        encoding="utf-8",
    )
    settings = Settings.load(config_path)
    assert settings.fetch_count == 10
    assert settings.top_n == 5
    assert settings.collector_sources.taptap is False
    assert settings.rss_feeds[0]["source"] == "demo"


def test_settings_env_overrides_yaml(monkeypatch, tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
collectors:
  fetch_count: 10
  top_n: 5
  sources:
    rss: true
    huggingface: true
    taptap: true
rss_feeds: []
keywords: {}
pusher:
  wecom_webhook: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=from-yaml"
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv(
        "PUSHER_WECOM_WEBHOOK", "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=from-env"
    )
    settings = Settings.load(config_path)
    assert settings.wecom_webhook.endswith("from-env")


def test_validate_for_run_allows_empty_webhook_in_dry_run(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
collectors:
  fetch_count: 10
  top_n: 5
  sources:
    rss: true
    huggingface: true
    taptap: true
rss_feeds: []
keywords: {}
pusher:
  wecom_webhook: ""
""".strip(),
        encoding="utf-8",
    )
    settings = Settings.load(config_path)
    settings.validate_for_run(dry_run=True)  # should NOT raise


def test_validate_for_run_rejects_invalid_live_webhook(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
collectors:
  fetch_count: 10
  top_n: 5
  sources:
    rss: true
    huggingface: true
    taptap: true
rss_feeds: []
keywords: {}
pusher:
  wecom_webhook: "https://example.com/not-wecom"
""".strip(),
        encoding="utf-8",
    )
    settings = Settings.load(config_path)
    with pytest.raises(ValueError, match="wecom webhook"):
        settings.validate_for_run(dry_run=False)
