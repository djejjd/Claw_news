"""Tests for app/main.py — FastAPI entrypoints and scheduler."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_env_defaults = {
    "LLM_API_KEY": "sk-test",
    "LLM_BASE_URL": "https://api.example.com",
    "LLM_MODEL": "test-model",
    "WECOM_WEBHOOK_URL": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test",
    "TZ": "Asia/Shanghai",
    "NEWS_RSS_URLS": "https://example.com/rss",
}


@pytest.fixture(autouse=True)
def _set_env(monkeypatch):
    """Ensure env vars are set before app.main is imported."""
    for k, v in _env_defaults.items():
        monkeypatch.setenv(k, v)


def _make_mock_agent():
    mock = AsyncMock()
    mock.run_once.return_value = {
        "status": "ok",
        "fetched_count": 8,
        "pushed": True,
        "summary_preview": "今日 AI 新闻摘要...",
        "errors": [],
    }
    return mock


def _make_mock_agent_skipped():
    mock = AsyncMock()
    mock.run_once.return_value = {
        "status": "skipped",
        "fetched_count": 0,
        "pushed": False,
        "summary_preview": "",
        "errors": ["another run is in progress"],
    }
    return mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    def test_health_returns_200(self):
        """GET /health returns 200 with healthy status."""
        from fastapi.testclient import TestClient

        # Must import app.main AFTER env vars are set by the fixture
        with (
            patch("app.main.agent", _make_mock_agent()),
            patch("app.main.scheduler", MagicMock()),
        ):
            from app.main import app

            client = TestClient(app)
            resp = client.get("/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"

    def test_lifespan_does_not_trigger_startup_ingest(self):
        """Service startup should not launch an immediate ingest task."""
        from fastapi.testclient import TestClient

        with (
            patch("app.main.agent", _make_mock_agent()),
            patch("app.main.scheduler", MagicMock()),
        ):
            from app.main import app

            with TestClient(app):
                pass

    def test_health_includes_ingest_status(self):
        """GET /health exposes the latest ingest summary."""
        from fastapi.testclient import TestClient

        with (
            patch("app.main.agent", _make_mock_agent()),
            patch("app.main.scheduler", MagicMock()),
            patch("app.main.IngestStatusStore") as mock_store,
        ):
            from app.main import app

            mock_store.return_value.load_status.return_value = {
                "last_ingest_at": "2026-05-18T08:00:00",
                "last_item_count": 3,
                "successful_sources": ["rss"],
                "failed_sources": [],
            }
            client = TestClient(app)
            resp = client.get("/health")

        assert resp.status_code == 200
        assert resp.json()["ingest"]["last_item_count"] == 3

    def test_root_returns_200(self):
        """GET / returns 200 with service info."""
        from fastapi.testclient import TestClient

        with (
            patch("app.main.agent", _make_mock_agent()),
            patch("app.main.scheduler", MagicMock()),
        ):
            from app.main import app

            client = TestClient(app)
            resp = client.get("/")

        assert resp.status_code == 200
        data = resp.json()
        assert "service" in data
        assert data["service"] == "Claw_news AI Assistant"


class TestRunNewsEndpoint:
    def test_run_news_triggers_agent(self):
        """POST /run/news calls run_pipeline() and returns its result."""
        from fastapi.testclient import TestClient

        from app.tools.summary_result import PublishResult

        mock_result = PublishResult(
            status="ok", selected_count=8, pushed=True,
            message_type="markdown", summary_preview="今日 AI 新闻摘要...",
            errors=[],
        )

        with (
            patch("app.main.run_pipeline", new=AsyncMock(return_value=mock_result)),
            patch("app.main.agent", _make_mock_agent()),
            patch("app.main.scheduler", MagicMock()),
        ):
            from app.main import app

            client = TestClient(app)
            resp = client.post("/run/news")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["fetched_count"] == 8
        assert data["pushed"] is True

    def test_run_news_when_skipped(self):
        """POST /run/news returns skipped status when lock held."""
        from fastapi.testclient import TestClient

        mock_agent = _make_mock_agent_skipped()

        with (
            patch("app.main.agent", mock_agent),
            patch("app.main.scheduler", MagicMock()),
        ):
            from app.main import app

            client = TestClient(app)
            resp = client.post("/run/news")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "skipped"



class TestScheduler:
    def test_scheduler_registers_three_cron_jobs(self):
        """The scheduler has exactly 2 jobs: 1 publish (09:00 cron) + 1 ingest (30m interval)."""
        from app.scheduler.jobs import create_scheduler

        mock_agent = _make_mock_agent()
        sched = create_scheduler(mock_agent, "Asia/Shanghai")

        jobs = sched.get_jobs()
        assert len(jobs) == 2

        # The publish job runs at 09:00 cron
        cron_jobs = [j for j in jobs if j.id == "publish_0900"]
        assert len(cron_jobs) == 1
        assert cron_jobs[0].trigger.fields[5].expressions[0].first == 9

        for job in jobs:
            assert str(job.trigger.timezone) == "Asia/Shanghai"

    def test_scheduler_jobs_call_agent_run_once(self):
        """The publish job is bound to agent.run_once."""
        from app.scheduler.jobs import create_scheduler

        mock_agent = _make_mock_agent()
        sched = create_scheduler(mock_agent, "Asia/Shanghai")

        # The publish job calls agent.run_once
        publish_jobs = [j for j in sched.get_jobs() if j.id == "publish_0900"]
        assert len(publish_jobs) == 1
        assert publish_jobs[0].func == mock_agent.run_once

    def test_scheduler_uses_configured_timezone(self):
        """TZ from config is respected."""
        from app.scheduler.jobs import create_scheduler

        mock_agent = _make_mock_agent()
        sched = create_scheduler(mock_agent, "Asia/Tokyo")

        for job in sched.get_jobs():
            assert str(job.trigger.timezone) == "Asia/Tokyo"

    def test_scheduler_no_duplicate_registration(self):
        """Calling create_scheduler twice creates independent schedulers."""
        from app.scheduler.jobs import create_scheduler

        mock_agent = _make_mock_agent()
        sched1 = create_scheduler(mock_agent, "Asia/Shanghai")
        sched2 = create_scheduler(mock_agent, "Asia/Shanghai")

        assert len(sched1.get_jobs()) == 2
        assert len(sched2.get_jobs()) == 2
        assert sched1 is not sched2
