"""Tests for app/main.py — FastAPI entrypoints and scheduler."""

import asyncio
import importlib
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.pipeline.candidate import CandidateItem
from app.publication.store import PublicationStore
from app.storage.ingest_status_store import IngestStatusStore

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


def _public_digest_store(tmp_path) -> PublicationStore:
    store = PublicationStore(f"sqlite:///{tmp_path / 'publication.db'}")
    store.create_schema()
    store.publish_articles(
        [
            CandidateItem(
                title="日报文章",
                url="https://example.test/digest",
                summary="来源摘要",
                source="example",
                category="ai",
                published_at="2026-08-16T08:00:00+00:00",
                fetched_at="2026-08-16T08:01:00+00:00",
                canonical_key="example.test/digest",
            )
        ]
    )
    store.publish_digest(
        digest_date="2026-08-16",
        version=1,
        published_at=datetime(2026, 8, 16, 9, tzinfo=timezone.utc),
        daily_judgement="今日判断",
        items=[
            {
                "canonical_key": "example.test/digest",
                "position": 1,
                "core_summary": "核心摘要",
                "importance": "high",
                "trend": "up",
                "topic_label": "AI",
            }
        ],
        github_projects=[{"full_name": "example/project", "recommendation": "推荐理由"}],
    )
    return store


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
        assert data["status"] in {"healthy", "degraded"}

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

    def test_health_does_not_degrade_before_failure_threshold(self):
        """Optional source skipped once is observable but does not cross the degraded threshold."""
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
        assert data["status"] == "healthy"
        assert "github" not in data["sources"]

    def test_health_degrades_when_publication_is_pending(self):
        """发布库待重试必须是可观察的降级状态。"""
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
                "skipped_sources": [],
                "publication": {"status": "pending", "error": "write: OperationalError"},
            }

            response = TestClient(main_module.app).get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "degraded"

    def test_health_degrades_when_publication_database_is_unreachable(self):
        """启用网站发布时，数据库连接失败必须直接可见。"""
        from fastapi.testclient import TestClient

        main_module = _load_app_module()
        publisher = MagicMock()
        publisher.store.healthcheck.side_effect = OSError("connection refused")

        with (
            patch.object(main_module, "agent", _make_mock_agent()),
            patch.object(main_module, "scheduler", MagicMock()),
            patch.object(
                main_module,
                "config",
                SimpleNamespace(publication_enabled=True, tz="Asia/Shanghai"),
            ),
            patch("app.publication.publisher.Publisher.from_config", return_value=publisher),
        ):
            response = TestClient(main_module.app).get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "degraded"
        assert response.json()["publication"]["status"] == "unhealthy"

    def test_health_exposes_structured_degraded_source(self):
        from fastapi.testclient import TestClient

        main_module = _load_app_module()
        with (
            patch.object(main_module, "agent", _make_mock_agent()),
            patch.object(main_module, "scheduler", MagicMock()),
            patch.object(main_module, "IngestStatusStore") as mock_store,
        ):
            mock_store.return_value.load_status.return_value = {
                "last_ingest_at": "2099-05-18T08:00:00",
                "successful_sources": [],
                "failed_sources": [],
                "skipped_sources": [],
                "degraded_sources": [{"source": "huggingface", "consecutive_failure_count": 3}],
            }
            data = TestClient(main_module.app).get("/health").json()

        assert data["status"] == "degraded"
        assert data["sources"]["huggingface"] == "degraded"

    def test_failed_source_is_not_overwritten_by_degraded_history(self):
        from fastapi.testclient import TestClient

        main_module = _load_app_module()
        with (
            patch.object(main_module, "agent", _make_mock_agent()),
            patch.object(main_module, "scheduler", MagicMock()),
            patch.object(main_module, "IngestStatusStore") as mock_store,
        ):
            mock_store.return_value.load_status.return_value = {
                "last_ingest_at": "2099-05-18T08:00:00",
                "successful_sources": [],
                "failed_sources": ["huggingface: timeout"],
                "skipped_sources": [],
                "degraded_sources": [{"source": "huggingface", "consecutive_failure_count": 3}],
            }
            data = TestClient(main_module.app).get("/health").json()

        assert data["sources"]["huggingface"] == "failed"

    def test_health_handles_offset_ingest_timestamp(self):
        """带时区的采集时间按真实时刻转换，不直接丢弃 offset。"""
        from fastapi.testclient import TestClient

        main_module = _load_app_module()
        with (
            patch.object(main_module, "agent", _make_mock_agent()),
            patch.object(main_module, "scheduler", MagicMock()),
            patch.object(main_module, "IngestStatusStore") as mock_store,
            patch.object(main_module, "local_now", return_value=datetime(2026, 5, 18, 9)),
        ):
            mock_store.return_value.load_status.return_value = {
                "last_ingest_at": "2026-05-18T00:30:00+00:00",
                "successful_sources": [],
                "failed_sources": [],
                "skipped_sources": [],
            }
            data = TestClient(main_module.app).get("/health").json()

        assert data["ingest_fresh"] is True

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

    def test_root_reports_package_version(self):
        """接口版本应来自安装包元数据，避免与项目版本漂移。"""
        from fastapi.testclient import TestClient

        main_module = _load_app_module()
        with (
            patch.object(main_module, "agent", _make_mock_agent()),
            patch.object(main_module, "scheduler", MagicMock()),
        ):
            data = TestClient(main_module.app).get("/").json()

        assert data["version"] == main_module.APP_VERSION
        assert main_module.app.version == main_module.APP_VERSION


class TestPublicDigestEndpoint:
    def test_digest_returns_the_default_local_day_with_public_fields_only(self, tmp_path):
        from fastapi.testclient import TestClient

        main_module = _load_app_module()
        store = _public_digest_store(tmp_path)
        config = SimpleNamespace(
            publication_enabled=True,
            publication_database_url=str(store.engine.url),
            tz="UTC",
        )

        with (
            patch.object(main_module.app.state, "config", config),
            patch("app.publication.routes.local_now", return_value=datetime(2026, 8, 16)),
        ):
            response = TestClient(main_module.app).get("/api/public/digests")

        assert response.status_code == 200
        assert response.json() == {
            "date": "2026-08-16",
            "version": 1,
            "published_at": "2026-08-16T09:00:00+00:00",
            "daily_judgement": "今日判断",
            "items": [
                {
                    "position": 1,
                    "core_summary": "核心摘要",
                    "importance": "high",
                    "trend": "up",
                    "topic_label": "AI",
                    "article": {
                        "id": 1,
                        "title": "日报文章",
                        "original_url": "https://example.test/digest",
                        "category": "ai",
                        "topic": None,
                        "summary": "来源摘要",
                        "published_at": "2026-08-16T08:00:00+00:00",
                        "fetched_at": "2026-08-16T08:01:00+00:00",
                        "source": {
                            "name": "example",
                            "display_name": "example",
                            "site_url": None,
                        },
                    },
                }
            ],
            "github_projects": [
                {
                    "position": 1,
                    "full_name": "example/project",
                    "recommendation": "推荐理由",
                }
            ],
        }

    @pytest.mark.parametrize("value", ["20260816", "2026-08-32"])
    def test_digest_rejects_invalid_date_with_the_public_error_contract(self, value):
        from fastapi.testclient import TestClient

        main_module = _load_app_module()

        response = TestClient(main_module.app).get(f"/api/public/digests?date={value}")

        assert response.status_code == 422
        assert response.json() == {"detail": {"code": "invalid_request", "message": "请求参数无效"}}

    def test_digest_returns_not_found_for_an_absent_date(self, tmp_path):
        from fastapi.testclient import TestClient

        main_module = _load_app_module()
        store = _public_digest_store(tmp_path)
        config = SimpleNamespace(
            publication_enabled=True,
            publication_database_url=str(store.engine.url),
            tz="UTC",
        )

        with patch.object(main_module.app.state, "config", config):
            response = TestClient(main_module.app).get("/api/public/digests?date=2026-08-15")

        assert response.status_code == 404
        assert response.json() == {
            "detail": {"code": "digest_not_found", "message": "指定日期不存在已发布日报"}
        }

    def test_digest_hides_unavailable_database_details(self):
        from fastapi.testclient import TestClient

        main_module = _load_app_module()
        config = SimpleNamespace(
            publication_enabled=True,
            publication_database_url="not-a-database-url",
            tz="UTC",
        )

        with patch.object(main_module.app.state, "config", config):
            response = TestClient(main_module.app).get("/api/public/digests?date=2026-08-16")

        assert response.status_code == 503
        assert response.json() == {
            "detail": {"code": "publication_unavailable", "message": "公共内容服务暂不可用"}
        }

    def test_digest_request_has_no_pipeline_or_persistence_side_effects(self, tmp_path):
        from fastapi.testclient import TestClient

        main_module = _load_app_module()
        store = _public_digest_store(tmp_path)
        config = SimpleNamespace(
            publication_enabled=True,
            publication_database_url=str(store.engine.url),
            tz="UTC",
        )
        before_tables = (store.count_articles(), store.count_digests(), store.count_digest_items())
        status_store = IngestStatusStore(tmp_path)
        status_store.write_status({"last_ingest_at": "2026-08-16T08:00:00"})
        status_path = status_store.path
        before_status = status_path.read_bytes()

        with (
            patch.object(main_module.app.state, "config", config),
            patch.object(main_module, "IngestStatusStore", return_value=status_store),
            patch.object(main_module.agent, "run_once", new_callable=AsyncMock) as run_once,
            patch("app.storage.ingest_status_store.IngestStatusStore.write_status") as write_status,
            patch("app.storage.ingestion_store.IngestionStore.append_or_merge") as append_or_merge,
            patch("app.tools.llm.summarize_news", new_callable=AsyncMock) as summarize_news,
            patch("pusher.wecom.WeComPusher.push", new_callable=AsyncMock) as push,
        ):
            response = TestClient(main_module.app).get("/api/public/digests?date=2026-08-16")

        assert response.status_code == 200
        assert (
            store.count_articles(),
            store.count_digests(),
            store.count_digest_items(),
        ) == before_tables
        assert status_path.read_bytes() == before_status
        run_once.assert_not_awaited()
        write_status.assert_not_called()
        append_or_merge.assert_not_called()
        summarize_news.assert_not_awaited()
        push.assert_not_awaited()


class TestPublicSourcesEndpoint:
    def test_sources_return_public_fields_from_the_main_app(self, tmp_path):
        from fastapi.testclient import TestClient

        main_module = _load_app_module()
        store = _public_digest_store(tmp_path)
        store.publish_sources(
            [
                {
                    "name": "example",
                    "display_name": "示例来源",
                    "default_category": "ai",
                    "site_url": "https://example.test",
                    "is_enabled": False,
                }
            ]
        )
        config = SimpleNamespace(
            publication_enabled=True,
            publication_database_url=str(store.engine.url),
            tz="UTC",
        )

        with (
            patch.object(main_module.app.state, "config", config),
            patch("app.publication.routes.local_now", return_value=datetime(2026, 8, 16)),
        ):
            response = TestClient(main_module.app).get("/api/public/sources")

        assert response.status_code == 200
        assert response.json() == [
            {
                "name": "example",
                "display_name": "示例来源",
                "site_url": "https://example.test",
            }
        ]

    def test_sources_hide_unavailable_database_details(self):
        from fastapi.testclient import TestClient

        main_module = _load_app_module()
        config = SimpleNamespace(
            publication_enabled=True,
            publication_database_url="not-a-database-url",
            tz="UTC",
        )

        with patch.object(main_module.app.state, "config", config):
            response = TestClient(main_module.app).get("/api/public/sources")

        assert response.status_code == 503
        assert response.json() == {
            "detail": {"code": "publication_unavailable", "message": "公共内容服务暂不可用"}
        }


class TestPublicApiContractRegression:
    def test_all_public_endpoints_share_visibility_window_and_read_only_contract(self, tmp_path):
        from fastapi.testclient import TestClient

        from app.publication.models import Article

        main_module = _load_app_module()
        store = _public_digest_store(tmp_path)
        store.publish_articles(
            [
                CandidateItem(
                    title="第二来源文章",
                    url="https://example.test/other",
                    summary="第二来源摘要",
                    source="other",
                    category="tool",
                    published_at="2026-08-16T10:00:00+00:00",
                    fetched_at="2026-08-16T10:01:00+00:00",
                    canonical_key="example.test/other",
                ),
                CandidateItem(
                    title="隐藏文章",
                    url="https://example.test/hidden",
                    summary="不应公开",
                    source="hidden",
                    category="ai",
                    published_at="2026-08-16T11:00:00+00:00",
                    fetched_at="2026-08-16T11:01:00+00:00",
                    canonical_key="example.test/hidden",
                ),
            ]
        )
        with store._sessions.begin() as session:
            session.query(Article).filter_by(canonical_key="example.test/hidden").update(
                {"visibility": "hidden"}
            )
        config = SimpleNamespace(
            publication_enabled=True,
            publication_database_url=str(store.engine.url),
            tz="UTC",
        )
        before = (store.count_articles(), store.count_digests(), store.count_digest_items())
        status_store = IngestStatusStore(tmp_path)
        status_store.write_status({"last_ingest_at": "2026-08-16T08:00:00"})
        status_before = status_store.path.read_bytes()

        with (
            patch.object(main_module.app.state, "config", config),
            patch.object(main_module, "IngestStatusStore", return_value=status_store),
            patch("app.publication.routes.local_now", return_value=datetime(2026, 8, 16)),
            patch("app.storage.ingest_status_store.IngestStatusStore.write_status") as write_status,
            patch("app.storage.ingestion_store.IngestionStore.append_or_merge") as append_or_merge,
            patch("app.tools.llm.summarize_news", new_callable=AsyncMock) as summarize_news,
            patch("pusher.wecom.WeComPusher.push", new_callable=AsyncMock) as push,
        ):
            client = TestClient(main_module.app)
            digest = client.get("/api/public/digests")
            articles = client.get("/api/public/articles?page_size=20")
            sources = client.get("/api/public/sources")

        assert digest.status_code == 200
        assert [item["title"] for item in articles.json()["items"]] == ["第二来源文章", "日报文章"]
        assert [source["name"] for source in sources.json()] == ["example", "other"]
        assert all("visibility" not in item for item in articles.json()["items"])
        assert all(
            "hidden" not in response.content.decode() for response in (digest, articles, sources)
        )
        assert status_store.path.read_bytes() == status_before
        write_status.assert_not_called()
        append_or_merge.assert_not_called()
        summarize_news.assert_not_awaited()
        push.assert_not_awaited()
        assert (store.count_articles(), store.count_digests(), store.count_digest_items()) == before


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
        fake_metrics_store.write_selection_eligible_counts.return_value = 2

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
            patch("collectors.ai_rss.load_feed_configuration", return_value=None),
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

        assert result.status == "ok"
        fake_metrics_store.write_selection_eligible_counts.assert_called_once()
        assert fake_metrics_store.write_selection_eligible_counts.call_args.args == (
            {"qbitai": 1, "huggingface": 1},
        )
        assert (
            "run_started_at" in fake_metrics_store.write_selection_eligible_counts.call_args.kwargs
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
        fake_metrics_store.write_selection_eligible_counts.return_value = 1

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
            patch("collectors.ai_rss.load_feed_configuration", return_value=None),
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

        assert result.status == "ok"
        assert "source_metrics_write_failed" not in result.errors


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
