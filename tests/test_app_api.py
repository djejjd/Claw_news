"""Tests for app/main.py — FastAPI entrypoints and scheduler."""

import asyncio
import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_REAL_PATH_EXISTS = Path.exists

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


def _load_app_module():
    class _DummyScheduler:
        def __init__(self, *args, **kwargs):
            self.jobs = []

        def add_job(self, *args, **kwargs):
            self.jobs.append((args, kwargs))

        def start(self):
            return None

        def shutdown(self, wait=False):
            return None

    scheduler_module = types.ModuleType("apscheduler.schedulers.asyncio")
    scheduler_module.AsyncIOScheduler = _DummyScheduler

    with patch.dict(sys.modules, {"apscheduler.schedulers.asyncio": scheduler_module}):
        return importlib.import_module("app.main")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    def test_health_returns_200(self):
        """GET /health returns 200 with healthy status."""
        from fastapi.testclient import TestClient

        main_module = _load_app_module()

        def _path_exists(path_obj: Path) -> bool:
            return False if path_obj.name == "publish_status.json" else _REAL_PATH_EXISTS(path_obj)

        with (
            patch.object(main_module, "agent", _make_mock_agent()),
            patch.object(main_module, "scheduler", MagicMock()),
            patch("pathlib.Path.exists", autospec=True, side_effect=_path_exists),
        ):
            client = TestClient(main_module.app)
            resp = client.get("/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"

    def test_lifespan_does_not_trigger_startup_ingest(self):
        """Service startup should not launch an immediate ingest task."""
        from fastapi.testclient import TestClient

        main_module = _load_app_module()
        with (
            patch.object(main_module, "agent", _make_mock_agent()),
            patch.object(main_module, "scheduler", MagicMock()),
        ):
            with TestClient(main_module.app):
                pass

    def test_health_includes_ingest_status(self):
        """GET /health exposes the latest ingest summary."""
        from fastapi.testclient import TestClient

        main_module = _load_app_module()
        def _path_exists(path_obj: Path) -> bool:
            return False if path_obj.name == "publish_status.json" else _REAL_PATH_EXISTS(path_obj)

        with (
            patch.object(main_module, "agent", _make_mock_agent()),
            patch.object(main_module, "scheduler", MagicMock()),
            patch.object(main_module, "IngestStatusStore") as mock_store,
            patch("pathlib.Path.exists", autospec=True, side_effect=_path_exists),
        ):
            mock_store.return_value.load_status.return_value = {
                "last_ingest_at": "2026-05-18T08:00:00",
                "last_item_count": 3,
                "successful_sources": ["rss"],
                "failed_sources": [],
                "skipped_sources": [],
            }
            client = TestClient(main_module.app)
            resp = client.get("/health")

        assert resp.status_code == 200
        assert resp.json()["ingest"]["last_item_count"] == 3

    def test_health_is_degraded_when_source_is_skipped(self):
        """Skipped source should pull overall health down to degraded."""
        from fastapi.testclient import TestClient

        main_module = _load_app_module()
        with (
            patch.object(main_module, "agent", _make_mock_agent()),
            patch.object(main_module, "scheduler", MagicMock()),
            patch.object(main_module, "IngestStatusStore") as mock_store,
        ):
            mock_store.return_value.load_status.return_value = {
                "last_ingest_at": "2099-05-18T08:00:00",
                "last_item_count": 3,
                "successful_sources": ["rss"],
                "failed_sources": [],
                "skipped_sources": ["github: optional"],
            }

            client = TestClient(main_module.app)
            resp = client.get("/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "degraded"
        assert data["sources"]["github"] == "degraded"

    def test_root_returns_200(self):
        """GET / returns 200 with service info."""
        from fastapi.testclient import TestClient

        main_module = _load_app_module()
        with (
            patch.object(main_module, "agent", _make_mock_agent()),
            patch.object(main_module, "scheduler", MagicMock()),
        ):
            client = TestClient(main_module.app)
            resp = client.get("/")

        assert resp.status_code == 200
        data = resp.json()
        assert "service" in data
        assert data["service"] == "Claw_news AI Assistant"


class TestRunNewsEndpoint:
    def test_run_news_triggers_agent(self):
        """POST /run/news calls the shared agent so publish locking is reused."""
        from fastapi.testclient import TestClient

        mock_agent = _make_mock_agent()

        main_module = _load_app_module()
        with (
            patch.object(main_module, "agent", mock_agent),
            patch.object(main_module, "scheduler", MagicMock()),
        ):
            client = TestClient(main_module.app)
            resp = client.post("/run/news")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["fetched_count"] == 8
        assert data["pushed"] is True
        mock_agent.run_once.assert_awaited_once_with(trigger_mode="http")

    def test_run_news_when_skipped(self):
        """POST /run/news returns skipped status when lock held."""
        from fastapi.testclient import TestClient

        mock_agent = _make_mock_agent_skipped()

        main_module = _load_app_module()
        with (
            patch.object(main_module, "agent", mock_agent),
            patch.object(main_module, "scheduler", MagicMock()),
        ):
            client = TestClient(main_module.app)
            resp = client.post("/run/news")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "skipped"

    def test_run_news_source_metrics_write_receives_source_counts(self):
        """The publish chain groups selections by source and writes the counts back."""
        from app.pipeline.context import RunContext
        from app.pipeline.news_pipeline import run_pipeline

        selected_items = [
            SimpleNamespace(
                title="A",
                url="https://example.com/a",
                summary="summary a",
                published_at="2026-05-19",
                source="qbitai",
                category="ai",
                canonical_key="example.com/a",
            ),
            SimpleNamespace(
                title="B",
                url="https://example.com/b",
                summary="summary b",
                published_at="2026-05-19",
                source="huggingface",
                category="ai",
                canonical_key="example.com/b",
            ),
        ]
        fake_metrics_store = MagicMock()
        fake_metrics_store.write_selected_counts.return_value = 2

        with (
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_ingestion_store,
            patch("app.pipeline.news_pipeline.TopicClassifier"),
            patch("app.pipeline.news_pipeline.Merger") as mock_merger_cls,
            patch(
                "app.pipeline.news_pipeline.summarize_news",
                new=AsyncMock(
                    return_value={
                        "headline_items": [
                            {
                                "title": "A",
                                "url": "https://example.com/a",
                                "core_summary": "a",
                                "importance": "高",
                                "trend": "up",
                            }
                        ],
                        "daily_judgement": "ok",
                    }
                ),
            ),
            patch("app.pipeline.news_pipeline.GitHubStore") as mock_github_store,
            patch("app.pipeline.news_pipeline.render_digest", return_value="markdown"),
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_pusher_cls,
            patch("app.pipeline.news_pipeline.StateStore") as mock_state_store_cls,
            patch(
                "app.pipeline.news_pipeline.SourceMetricsStore",
                return_value=fake_metrics_store,
            ),
            patch("app.pipeline.news_pipeline._collect_source_failures", return_value=[]),
        ):
            mock_ingestion_store.return_value.load_window_candidates.return_value = selected_items
            mock_merger_cls.return_value.merge.return_value = selected_items
            mock_github_store.return_value.load_latest_snapshot.return_value = []
            mock_pusher_cls.return_value.push_single_markdown = AsyncMock(
                return_value=MagicMock(success=True)
            )
            mock_state_store_cls.return_value.load_pushed_urls.return_value = set()
            mock_state_store_cls.return_value.load_published_keys.return_value = set()

            result = asyncio.run(
                run_pipeline(
                    RunContext(
                        trigger_mode="http",
                        time_window_start="2026-05-19T00:00:00",
                        time_window_end="2026-05-19T09:00:00",
                    ),
                    MagicMock(
                        llm_base_url="https://api.example.com",
                        llm_api_key="sk-test",
                        llm_model="test-model",
                        wecom_webhook_url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test",
                    ),
                )
            )

        assert result.status == "degraded"  # push ok but source_metrics write short
        fake_metrics_store.write_selected_counts.assert_called_once_with(
            {"qbitai": 1, "huggingface": 1}
        )

    def test_run_news_records_error_when_source_metrics_write_is_short(self):
        """If the metrics store writes fewer sources than expected, the result carries an error."""
        from app.pipeline.context import RunContext
        from app.pipeline.news_pipeline import run_pipeline

        selected_items = [
            SimpleNamespace(
                title="A",
                url="https://example.com/a",
                summary="summary a",
                published_at="2026-05-19",
                source="qbitai",
                category="ai",
                canonical_key="example.com/a",
            ),
            SimpleNamespace(
                title="B",
                url="https://example.com/b",
                summary="summary b",
                published_at="2026-05-19",
                source="huggingface",
                category="ai",
                canonical_key="example.com/b",
            ),
        ]
        fake_metrics_store = MagicMock()
        fake_metrics_store.write_selected_counts.return_value = 1

        with (
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_ingestion_store,
            patch("app.pipeline.news_pipeline.TopicClassifier"),
            patch("app.pipeline.news_pipeline.Merger") as mock_merger_cls,
            patch(
                "app.pipeline.news_pipeline.summarize_news",
                new=AsyncMock(
                    return_value={
                        "headline_items": [
                            {
                                "title": "A",
                                "url": "https://example.com/a",
                                "core_summary": "a",
                                "importance": "高",
                                "trend": "up",
                            }
                        ],
                        "daily_judgement": "ok",
                    }
                ),
            ),
            patch("app.pipeline.news_pipeline.GitHubStore") as mock_github_store,
            patch("app.pipeline.news_pipeline.render_digest", return_value="markdown"),
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_pusher_cls,
            patch("app.pipeline.news_pipeline.StateStore") as mock_state_store_cls,
            patch(
                "app.pipeline.news_pipeline.SourceMetricsStore",
                return_value=fake_metrics_store,
            ),
            patch("app.pipeline.news_pipeline._collect_source_failures", return_value=[]),
        ):
            mock_ingestion_store.return_value.load_window_candidates.return_value = selected_items
            mock_merger_cls.return_value.merge.return_value = selected_items
            mock_github_store.return_value.load_latest_snapshot.return_value = []
            mock_pusher_cls.return_value.push_single_markdown = AsyncMock(
                return_value=MagicMock(success=True)
            )
            mock_state_store_cls.return_value.load_pushed_urls.return_value = set()
            mock_state_store_cls.return_value.load_published_keys.return_value = set()

            result = asyncio.run(
                run_pipeline(
                    RunContext(
                        trigger_mode="http",
                        time_window_start="2026-05-19T00:00:00",
                        time_window_end="2026-05-19T09:00:00",
                    ),
                    MagicMock(
                        llm_base_url="https://api.example.com",
                        llm_api_key="sk-test",
                        llm_model="test-model",
                        wecom_webhook_url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test",
                    ),
                )
            )

        assert result.status == "degraded"  # push ok but state write partially failed
        assert "source_metrics_write_failed" in result.errors


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

    def test_ingest_scheduler_job_prevents_overlap(self):
        """The ingest interval job should coalesce and disallow overlap."""
        from app.scheduler.jobs import create_scheduler

        mock_agent = _make_mock_agent()
        sched = create_scheduler(mock_agent, "Asia/Shanghai")

        ingest_jobs = [j for j in sched.get_jobs() if j.id == "ingest_30m"]
        assert len(ingest_jobs) == 1
        assert ingest_jobs[0].max_instances == 1
        assert ingest_jobs[0].coalesce is True
