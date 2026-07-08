"""Tests for the legacy CLI compatibility entrypoint."""

import pytest


@pytest.mark.asyncio
async def test_dry_run_does_not_require_publish_configuration(tmp_path, monkeypatch):
    """Dry-run should be available without LLM or WeCom environment variables."""
    import main as cli_main

    for name in ["LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL", "WECOM_WEBHOOK_URL"]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(cli_main, "DATA_DIR", tmp_path)

    await cli_main.main(period="morning", dry_run=True)
