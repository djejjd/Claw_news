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
        """POST /run/news calls agent.run_once() and returns its result."""
        from fastapi.testclient import TestClient

        mock_agent = _make_mock_agent()

        with (
            patch("app.main.agent", mock_agent),
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
        mock_agent.run_once.assert_awaited_once()

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
        """The scheduler has exactly 3 jobs at 09:00, 14:00, 20:00."""
        from app.scheduler.jobs import create_scheduler

        mock_agent = _make_mock_agent()
        sched = create_scheduler(mock_agent, "Asia/Shanghai")

        jobs = sched.get_jobs()
        assert len(jobs) == 3

        hours = sorted(j.trigger.fields[5].expressions[0].first for j in jobs)
        assert hours == [9, 14, 20]

        for job in jobs:
            assert str(job.trigger.timezone) == "Asia/Shanghai"

    def test_scheduler_jobs_call_agent_run_once(self):
        """Jobs are bound to agent.run_once."""
        from app.scheduler.jobs import create_scheduler

        mock_agent = _make_mock_agent()
        sched = create_scheduler(mock_agent, "Asia/Shanghai")

        for job in sched.get_jobs():
            assert job.func == mock_agent.run_once

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

        assert len(sched1.get_jobs()) == 3
        assert len(sched2.get_jobs()) == 3
        assert sched1 is not sched2
