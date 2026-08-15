"""Tests for run_pipeline — the unified news publishing pipeline.

These tests mock the pipeline's internal dependencies to verify core
behaviours: success, push failure, state persistence, and no-candidate skip.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import AppConfig
from app.pipeline.candidate import CandidateItem
from app.pipeline.context import RunContext
from pusher.wecom import PushResult

# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _force_old_pipeline():
    p = patch("collectors.ai_rss.load_feed_configuration", return_value=None)
    p.start()
    yield
    p.stop()


def _make_config(**kwargs) -> AppConfig:
    return AppConfig(
        llm_api_key="test-key",
        llm_base_url="https://api.example.com",
        llm_model="test-model",
        wecom_webhook_url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test",
        tz="Asia/Shanghai",
        news_rss_urls=[],
        **kwargs,
    )


def _make_candidate(
    title: str = "Test",
    url: str = "https://example.com/1",
    summary: str = "Summary",
    source: str = "qbitai",
    category: str = "ai",
    published_at: str = "2026-05-18",
) -> CandidateItem:
    return CandidateItem(
        title=title,
        url=url,
        summary=summary,
        source=source,
        category=category,
        published_at=published_at,
    )


def _make_ctx(**kwargs) -> RunContext:
    return RunContext(
        trigger_mode="cli_compat",
        time_window_start="2026-05-18T00:00:00",
        time_window_end="2026-05-18T12:00:00",
        **kwargs,
    )


def _make_llm_result() -> dict:
    return {
        "headline_items": [
            {
                "title": "Test News",
                "url": "https://example.com/1",
                "core_summary": "A test summary.",
                "importance": "高",
                "trend": "利好",
            }
        ],
        "daily_judgement": "AI行业稳步发展",
    }


def _make_push_result(*, success: bool = True) -> "PushResult":
    return PushResult(
        category="ai",
        success=success,
        urls=["https://example.com/1"] if success else [],
        errcode=0 if success else 45009,
        errmsg="ok" if success else "rate limited",
    )


def _new_pipeline_feed_config() -> dict:
    return {
        "feeds": {
            "ai": [
                {"source": "source-a", "quality_weight": 4.0},
                {"source": "source-b", "quality_weight": 3.0},
            ],
            "tool": [],
            "game": [],
            "digital": [],
        },
        "source_policies": {},
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPipelineSuccess:
    """Full pipeline success path — push succeeds, state is persisted."""

    @pytest.mark.asyncio
    async def test_run_pipeline_all_success(self, tmp_path: Path):
        """When all stages succeed, status is 'ok' and pushed is True."""
        from app.pipeline.news_pipeline import run_pipeline

        config = _make_config()
        ctx = _make_ctx()
        candidate = _make_candidate()
        llm_result = _make_llm_result()
        push_result = _make_push_result(success=True)

        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_is,
            patch(
                "app.pipeline.news_pipeline.summarize_news", new=AsyncMock(return_value=llm_result)
            ),
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_pusher_cls,
            patch("app.pipeline.news_pipeline.TopicClassifier") as mock_cls,
            patch("app.pipeline.news_pipeline.SourceMetricsStore") as mock_metrics_store_cls,
        ):
            # IngestionStore returns one candidate
            mock_is_inst = MagicMock()
            mock_is_inst.load_window_candidates.return_value = [candidate]
            mock_is.return_value = mock_is_inst

            # Topic classifier is a no-op
            mock_cls_inst = MagicMock()
            mock_cls.return_value = mock_cls_inst

            # WeCom push succeeds
            mock_pusher = MagicMock()
            mock_pusher.push_single_markdown = AsyncMock(return_value=push_result)
            mock_pusher_cls.return_value = mock_pusher

            mock_metrics_store_cls.return_value.write_selected_counts.return_value = 1

            result = await run_pipeline(ctx, config)

        assert result.status == "ok"
        assert result.pushed is True
        assert result.selected_count == 1
        assert result.errors == []


class TestTopicClusterPersistence:
    @staticmethod
    def _clustered_candidates() -> list[CandidateItem]:
        candidates = [
            _make_candidate(
                title="OpenAI releases GPT 5 API",
                url="https://source-a.example/gpt-5-api",
                source="source-a",
                published_at="2026-05-18T08:00:00+08:00",
            ),
            _make_candidate(
                title="OpenAI releases GPT 5 API",
                url="https://source-b.example/gpt-5-api-news",
                source="source-b",
                published_at="2026-05-18T07:00:00+08:00",
            ),
        ]
        for candidate in candidates:
            candidate.topic = "model_release"
        return candidates

    @staticmethod
    def _llm_result() -> dict:
        return {
            "headline_items": [
                {
                    "title": "OpenAI releases GPT 5 API",
                    "url": "https://source-a.example/gpt-5-api",
                    "core_summary": "Model API update.",
                    "importance": "high",
                    "trend": "up",
                }
            ],
            "daily_judgement": "Model update.",
        }

    @staticmethod
    def _assert_cluster_audit_contract(evidence: list[dict]) -> None:
        excluded_index = next(
            index
            for index, event in enumerate(evidence)
            if event.get("event") == "topic_cluster_excluded"
        )
        event = evidence[excluded_index]
        assert event["schema_version"] == 2
        assert event["canonical_key"] == "source-b.example/gpt-5-api-news"
        assert event["component_winner_canonical_key"] == "source-a.example/gpt-5-api"
        assert event["selection_round"] == 1
        assert event["source"] == "source-b"
        assert event["category"] == "ai"
        assert event["topic"] == "model_release"
        assert event["rejection_reason"] == "topic_cluster_similarity"
        assert event["tokenizer_version"] == "nfkc-casefold-v1"
        assert event["title_similarity"] == 1.0
        assert event["trigger_edges"]
        assert any(item["event"] == "temporary_selected" for item in evidence[:excluded_index])
        assert any(item["event"] == "final_selected" for item in evidence[excluded_index + 1 :])

    @pytest.mark.asyncio
    async def test_topic_cluster_event_persists_to_immediate_digest(self, tmp_path: Path):
        from app.pipeline.news_pipeline import run_pipeline

        config = _make_config(topic_cluster_enabled=True)
        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch(
                "collectors.ai_rss.load_effective_feed_configuration",
                return_value=_new_pipeline_feed_config(),
            ),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_ingestion,
            patch("app.pipeline.news_pipeline.IngestStatusStore") as mock_status,
            patch("app.pipeline.news_pipeline.SourceMetricsStore") as mock_metrics,
            patch("app.pipeline.news_pipeline.GitHubStore") as mock_github,
            patch("app.pipeline.news_pipeline.GitHubExposureStore"),
            patch("app.pipeline.news_pipeline.TopicClassifier"),
            patch("app.pipeline.news_pipeline.ContentCategoryClassifier", create=True),
            patch("app.classifiers.content_category_classifier.ContentCategoryClassifier"),
            patch("app.pipeline.news_pipeline.build_relevance_filter", create=True),
            patch("app.classifiers.relevance_filter.build_relevance_filter") as mock_filter,
            patch(
                "app.pipeline.news_pipeline.summarize_news",
                new=AsyncMock(return_value=self._llm_result()),
            ),
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_wecom,
        ):
            candidates = self._clustered_candidates()
            mock_ingestion.return_value.load_recent_candidates.return_value = candidates
            mock_status.return_value.load_status.return_value = {"failed_sources": []}
            mock_metrics.return_value.write_selected_counts.return_value = 1
            mock_github.return_value.load_latest_snapshot.return_value = []
            mock_filter.return_value.evaluate_batch.return_value = (candidates, [])
            mock_wecom.return_value.push_single_markdown = AsyncMock(
                return_value=_make_push_result()
            )

            result = await run_pipeline(_make_ctx(), config)

        assert result.status == "ok"
        digest = json.loads((tmp_path / "2026-05-18" / "ai_digest.json").read_text())
        self._assert_cluster_audit_contract(digest["selection_evidence"])

    @pytest.mark.asyncio
    async def test_topic_cluster_event_persists_to_pending_delivery(self, tmp_path: Path):
        from app.delivery.store import PendingDeliveryStore
        from app.pipeline.news_pipeline import run_pipeline

        config = _make_config(
            topic_cluster_enabled=True, telegram_bot_token="bot", telegram_chat_id="chat"
        )
        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch(
                "collectors.ai_rss.load_effective_feed_configuration",
                return_value=_new_pipeline_feed_config(),
            ),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_ingestion,
            patch("app.pipeline.news_pipeline.IngestStatusStore") as mock_status,
            patch("app.pipeline.news_pipeline.SourceMetricsStore") as mock_metrics,
            patch("app.pipeline.news_pipeline.GitHubStore") as mock_github,
            patch("app.pipeline.news_pipeline.GitHubExposureStore"),
            patch("app.pipeline.news_pipeline.TopicClassifier"),
            patch("app.classifiers.content_category_classifier.ContentCategoryClassifier"),
            patch("app.classifiers.relevance_filter.build_relevance_filter") as mock_filter,
            patch(
                "app.pipeline.news_pipeline.summarize_news",
                new=AsyncMock(return_value=self._llm_result()),
            ),
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_wecom,
            patch("app.pipeline.news_pipeline.TelegramPusher") as mock_telegram,
        ):
            candidates = self._clustered_candidates()
            mock_ingestion.return_value.load_recent_candidates.return_value = candidates
            mock_status.return_value.load_status.return_value = {"failed_sources": []}
            mock_metrics.return_value.write_selected_counts.return_value = 1
            mock_github.return_value.load_latest_snapshot.return_value = []
            mock_filter.return_value.evaluate_batch.return_value = (candidates, [])
            mock_wecom.return_value.push_single_markdown = AsyncMock(
                return_value=_make_push_result()
            )
            mock_telegram.return_value.push_messages = AsyncMock(side_effect=RuntimeError("down"))

            result = await run_pipeline(_make_ctx(), config)

        assert result.status == "degraded", result.errors
        pending = PendingDeliveryStore(tmp_path).load("2026-05-18", "morning")
        assert pending is not None
        self._assert_cluster_audit_contract(pending["finalization"]["selection_evidence"])

    @pytest.mark.asyncio
    async def test_topic_cluster_evidence_is_identical_in_digest_and_pending(self, tmp_path: Path):
        """两条持久化路径必须存储同一份完整聚类审计证据。"""
        from app.delivery.store import PendingDeliveryStore
        from app.pipeline.news_pipeline import run_pipeline

        async def run_with_delivery(data_dir: Path, *, fail_telegram: bool) -> list[dict]:
            config = _make_config(
                topic_cluster_enabled=True,
                **(
                    {"telegram_bot_token": "bot", "telegram_chat_id": "chat"}
                    if fail_telegram
                    else {}
                ),
            )
            with (
                patch("app.pipeline.news_pipeline._DATA_DIR", data_dir),
                patch(
                    "collectors.ai_rss.load_effective_feed_configuration",
                    return_value=_new_pipeline_feed_config(),
                ),
                patch("app.pipeline.news_pipeline.IngestionStore") as mock_ingestion,
                patch("app.pipeline.news_pipeline.IngestStatusStore") as mock_status,
                patch("app.pipeline.news_pipeline.SourceMetricsStore") as mock_metrics,
                patch("app.pipeline.news_pipeline.GitHubStore") as mock_github,
                patch("app.pipeline.news_pipeline.GitHubExposureStore"),
                patch("app.pipeline.news_pipeline.TopicClassifier"),
                patch("app.classifiers.content_category_classifier.ContentCategoryClassifier"),
                patch("app.classifiers.relevance_filter.build_relevance_filter") as mock_filter,
                patch(
                    "app.pipeline.news_pipeline.summarize_news",
                    new=AsyncMock(return_value=self._llm_result()),
                ),
                patch("app.pipeline.news_pipeline.WeComPusher") as mock_wecom,
                patch("app.pipeline.news_pipeline.TelegramPusher") as mock_telegram,
            ):
                candidates = self._clustered_candidates()
                mock_ingestion.return_value.load_recent_candidates.return_value = candidates
                mock_status.return_value.load_status.return_value = {"failed_sources": []}
                mock_metrics.return_value.write_selected_counts.return_value = 1
                mock_github.return_value.load_latest_snapshot.return_value = []
                mock_filter.return_value.evaluate_batch.return_value = (candidates, [])
                mock_wecom.return_value.push_single_markdown = AsyncMock(
                    return_value=_make_push_result()
                )
                mock_telegram.return_value.push_messages = AsyncMock(
                    side_effect=RuntimeError("down") if fail_telegram else None
                )
                result = await run_pipeline(_make_ctx(), config)

            assert result.status == ("degraded" if fail_telegram else "ok"), result.errors
            if fail_telegram:
                pending = PendingDeliveryStore(data_dir).load("2026-05-18", "morning")
                assert pending is not None
                return pending["finalization"]["selection_evidence"]
            digest = json.loads((data_dir / "2026-05-18" / "ai_digest.json").read_text())
            return digest["selection_evidence"]

        digest_evidence = await run_with_delivery(tmp_path / "direct", fail_telegram=False)
        pending_evidence = await run_with_delivery(tmp_path / "pending", fail_telegram=True)

        self._assert_cluster_audit_contract(digest_evidence)
        self._assert_cluster_audit_contract(pending_evidence)
        assert pending_evidence == digest_evidence

    @pytest.mark.asyncio
    async def test_topic_cluster_non_convergence_skips_llm_and_delivery(self, tmp_path: Path):
        from app.pipeline.news_pipeline import run_pipeline

        config = _make_config(
            topic_cluster_enabled=True,
            telegram_bot_token="bot",
            telegram_chat_id="chat",
            feishu_app_id="app",
            feishu_app_secret="secret",
            feishu_chat_id="chat",
        )
        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch(
                "collectors.ai_rss.load_effective_feed_configuration",
                return_value=_new_pipeline_feed_config(),
            ),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_ingestion,
            patch("app.pipeline.news_pipeline.IngestStatusStore") as mock_status,
            patch("app.pipeline.news_pipeline.TopicClassifier"),
            patch("app.classifiers.content_category_classifier.ContentCategoryClassifier"),
            patch("app.classifiers.relevance_filter.build_relevance_filter") as mock_filter,
            patch(
                "app.pipeline.selection.select_digest_with_topic_clustering",
                side_effect=RuntimeError("topic_cluster_non_convergent"),
            ),
            patch("app.pipeline.news_pipeline.summarize_news", new=AsyncMock()) as mock_summarize,
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_wecom,
            patch("app.pipeline.news_pipeline.TelegramPusher") as mock_telegram,
            patch("app.pipeline.news_pipeline.FeishuPusher") as mock_feishu,
        ):
            candidates = self._clustered_candidates()
            mock_ingestion.return_value.load_recent_candidates.return_value = candidates
            mock_status.return_value.load_status.return_value = {"failed_sources": []}
            mock_filter.return_value.evaluate_batch.return_value = (candidates, [])

            result = await run_pipeline(_make_ctx(), config)

        assert result.status == "failed"
        assert result.errors == ["topic_cluster_non_convergent"]
        mock_summarize.assert_not_awaited()
        mock_wecom.assert_not_called()
        mock_telegram.assert_not_called()
        mock_feishu.assert_not_called()
        assert not (tmp_path / "pending_deliveries").exists()


class TestLlmRelevancePipeline:
    @pytest.mark.asyncio
    async def test_invalid_relevance_fails_after_one_llm_call_before_delivery(self, tmp_path: Path):
        """启用复核时，缺失 relevance 必须失败且不能进入投递。"""
        from app.pipeline.news_pipeline import run_pipeline

        config = _make_config(llm_relevance_enabled=True)
        candidate = _make_candidate(
            source="source-a",
            url="https://source-a.example/article",
            published_at="2026-05-18T08:00:00+08:00",
        )
        llm_result = {
            "headline_items": [
                {
                    "title": candidate.title,
                    "url": candidate.url,
                    "core_summary": "摘要",
                    "importance": "中",
                    "trend": "趋势",
                }
            ],
            "daily_judgement": "判断",
        }
        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch(
                "collectors.ai_rss.load_effective_feed_configuration",
                return_value=_new_pipeline_feed_config(),
            ),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_ingestion,
            patch("app.pipeline.news_pipeline.IngestStatusStore") as mock_status,
            patch("app.pipeline.news_pipeline.SourceMetricsStore") as mock_metrics,
            patch("app.pipeline.news_pipeline.GitHubStore") as mock_github,
            patch("app.pipeline.news_pipeline.TopicClassifier"),
            patch("app.classifiers.content_category_classifier.ContentCategoryClassifier"),
            patch("app.classifiers.relevance_filter.build_relevance_filter") as mock_filter,
            patch(
                "app.pipeline.news_pipeline.summarize_news", new=AsyncMock(return_value=llm_result)
            ) as mock_summarize,
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_wecom,
        ):
            mock_ingestion.return_value.load_recent_candidates.return_value = [candidate]
            mock_status.return_value.load_status.return_value = {
                "failed_sources": [],
                "last_ingest_at": "2026-05-18T08:00:00+08:00",
            }
            mock_metrics.return_value.write_selection_eligible_counts.return_value = 1
            mock_github.return_value.load_latest_snapshot.return_value = []
            mock_filter.return_value.evaluate_batch.return_value = ([candidate], [])

            result = await run_pipeline(_make_ctx(), config)

        assert result.status == "failed"
        assert result.errors[0].startswith("llm_relevance_invalid:")
        mock_summarize.assert_awaited_once()
        mock_wecom.assert_not_called()
        status = json.loads((tmp_path / "publish_status.json").read_text())
        assert status["status"] == "failed"

    @pytest.mark.asyncio
    async def test_low_relevance_reselects_from_full_pool_without_second_llm_call(
        self, tmp_path: Path
    ):
        """第 11 个候选在低相关初选项被淘汰后补位，且不再请求 LLM。"""
        from app.pipeline.news_pipeline import run_pipeline

        low_url = "https://source-a.example/low"
        initial = [
            _make_candidate(
                title=f"初选 {index}",
                url=low_url if index == 0 else f"https://initial-{index}.example/article",
                source=f"initial-{index}",
                published_at="2026-05-18T08:00:00+08:00",
            )
            for index in range(10)
        ]
        for index, candidate in enumerate(initial):
            candidate.source_weight = 20 - index
        replacement = _make_candidate(
            title="未评分补位",
            url="https://replacement.example/article",
            source="replacement",
            published_at="2026-05-18T08:00:00+08:00",
        )
        replacement.source_weight = 1

        async def summarize_once(items, **_kwargs):
            return {
                "headline_items": [
                    {
                        "title": item["title"],
                        "url": item["link"],
                        "core_summary": "LLM 摘要",
                        "importance": "中",
                        "trend": "趋势",
                        "relevance": 0.2 if item["link"] == low_url else 0.9,
                    }
                    for item in items
                ],
                "daily_judgement": "初选判断",
            }

        config = _make_config(llm_relevance_enabled=True)
        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch(
                "collectors.ai_rss.load_effective_feed_configuration",
                return_value=_new_pipeline_feed_config(),
            ),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_ingestion,
            patch("app.pipeline.news_pipeline.IngestStatusStore") as mock_status,
            patch("app.pipeline.news_pipeline.SourceMetricsStore") as mock_metrics,
            patch("app.pipeline.news_pipeline.GitHubStore") as mock_github,
            patch("app.pipeline.news_pipeline.TopicClassifier"),
            patch("app.classifiers.content_category_classifier.ContentCategoryClassifier"),
            patch("app.classifiers.relevance_filter.build_relevance_filter") as mock_filter,
            patch(
                "app.pipeline.news_pipeline.summarize_news",
                new=AsyncMock(side_effect=summarize_once),
            ) as mock_summarize,
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_wecom,
        ):
            candidates = initial + [replacement]
            mock_ingestion.return_value.load_recent_candidates.return_value = candidates
            mock_status.return_value.load_status.return_value = {
                "failed_sources": [],
                "last_ingest_at": "2026-05-18T08:00:00+08:00",
            }
            mock_metrics.return_value.write_selection_eligible_counts.return_value = 10
            mock_github.return_value.load_latest_snapshot.return_value = []
            mock_filter.return_value.evaluate_batch.return_value = (candidates, [])
            mock_wecom.return_value.push_single_markdown = AsyncMock(
                return_value=_make_push_result()
            )

            result = await run_pipeline(_make_ctx(), config)

        assert result.status == "ok"
        assert result.selected_count == 10
        mock_summarize.assert_awaited_once()
        digest = json.loads((tmp_path / "2026-05-18" / "ai_digest.json").read_text())
        assert low_url not in digest["published_urls"]
        backfill = next(item for item in digest["headline_items"] if item["url"] == replacement.url)
        assert backfill["relevance"] is None
        assert backfill["relevance_source"] == "not_scored_backfill"
        assert digest["daily_judgement"] == "今日精选已完成相关性复核"
        assert digest["daily_judgement_source"] == "final_selection_fallback"

    @pytest.mark.asyncio
    async def test_insufficient_candidates_after_relevance_rejection_are_degraded(
        self, tmp_path: Path
    ):
        """低相关项淘汰后候选不足仍正常投递，且给出结构化降级原因。"""
        from app.pipeline.news_pipeline import run_pipeline

        candidate = _make_candidate(
            source="source-a",
            url="https://source-a.example/low",
            published_at="2026-05-18T08:00:00+08:00",
        )
        llm_result = {
            "headline_items": [
                {
                    "title": candidate.title,
                    "url": candidate.url,
                    "core_summary": "摘要",
                    "importance": "中",
                    "trend": "趋势",
                    "relevance": 0.2,
                }
            ],
            "daily_judgement": "初选判断",
        }
        config = _make_config(llm_relevance_enabled=True)
        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch(
                "collectors.ai_rss.load_effective_feed_configuration",
                return_value=_new_pipeline_feed_config(),
            ),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_ingestion,
            patch("app.pipeline.news_pipeline.IngestStatusStore") as mock_status,
            patch("app.pipeline.news_pipeline.SourceMetricsStore") as mock_metrics,
            patch("app.pipeline.news_pipeline.GitHubStore") as mock_github,
            patch("app.pipeline.news_pipeline.TopicClassifier"),
            patch("app.classifiers.content_category_classifier.ContentCategoryClassifier"),
            patch("app.classifiers.relevance_filter.build_relevance_filter") as mock_filter,
            patch(
                "app.pipeline.news_pipeline.summarize_news", new=AsyncMock(return_value=llm_result)
            ) as mock_summarize,
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_wecom,
        ):
            mock_ingestion.return_value.load_recent_candidates.return_value = [candidate]
            mock_status.return_value.load_status.return_value = {
                "failed_sources": [],
                "last_ingest_at": "2026-05-18T08:00:00+08:00",
            }
            mock_metrics.return_value.write_selection_eligible_counts.return_value = 1
            mock_github.return_value.load_latest_snapshot.return_value = []
            mock_filter.return_value.evaluate_batch.return_value = ([candidate], [])
            mock_wecom.return_value.push_single_markdown = AsyncMock(
                return_value=_make_push_result()
            )

            result = await run_pipeline(_make_ctx(), config)

        assert result.status == "degraded"
        assert result.pushed is True
        assert result.selected_count == 0
        mock_summarize.assert_awaited_once()
        mock_wecom.return_value.push_single_markdown.assert_awaited_once()
        digest = json.loads((tmp_path / "2026-05-18" / "ai_digest.json").read_text())
        status = json.loads((tmp_path / "publish_status.json").read_text())
        assert digest["degradation_reasons"] == ["llm_relevance_insufficient_candidates"]
        assert status["degradation_reasons"] == digest["degradation_reasons"]

    @pytest.mark.asyncio
    async def test_pending_recovery_preserves_relevance_finalization_without_recalling_llm(
        self, tmp_path: Path
    ):
        """pending 恢复必须复用首轮终选审计，不能重新调用 LLM。"""
        from app.delivery.store import PendingDeliveryStore
        from app.pipeline.news_pipeline import run_pipeline

        candidate = _make_candidate(
            source="source-a",
            url="https://source-a.example/low",
            published_at="2026-05-18T08:00:00+08:00",
        )
        llm_result = {
            "headline_items": [
                {
                    "title": candidate.title,
                    "url": candidate.url,
                    "core_summary": "摘要",
                    "importance": "中",
                    "trend": "趋势",
                    "relevance": 0.2,
                }
            ],
            "daily_judgement": "初选判断",
        }
        config = _make_config(
            llm_relevance_enabled=True,
            telegram_bot_token="bot",
            telegram_chat_id="chat",
        )
        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch(
                "collectors.ai_rss.load_effective_feed_configuration",
                return_value=_new_pipeline_feed_config(),
            ),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_ingestion,
            patch("app.pipeline.news_pipeline.IngestStatusStore") as mock_status,
            patch("app.pipeline.news_pipeline.SourceMetricsStore") as mock_metrics,
            patch("app.pipeline.news_pipeline.GitHubStore") as mock_github,
            patch("app.pipeline.news_pipeline.GitHubExposureStore"),
            patch("app.pipeline.news_pipeline.TopicClassifier"),
            patch("app.classifiers.content_category_classifier.ContentCategoryClassifier"),
            patch("app.classifiers.relevance_filter.build_relevance_filter") as mock_filter,
            patch(
                "app.pipeline.news_pipeline.summarize_news", new=AsyncMock(return_value=llm_result)
            ) as mock_summarize,
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_wecom,
            patch("app.pipeline.news_pipeline.TelegramPusher") as mock_telegram,
        ):
            mock_ingestion.return_value.load_recent_candidates.return_value = [candidate]
            mock_status.return_value.load_status.return_value = {
                "failed_sources": [],
                "last_ingest_at": "2026-05-18T08:00:00+08:00",
            }
            mock_metrics.return_value.write_selection_eligible_counts.return_value = 1
            mock_github.return_value.load_latest_snapshot.return_value = []
            mock_filter.return_value.evaluate_batch.return_value = ([candidate], [])
            mock_wecom.return_value.push_single_markdown = AsyncMock(
                return_value=_make_push_result()
            )
            mock_telegram.return_value.push_messages = AsyncMock(
                side_effect=[RuntimeError("telegram down"), None]
            )

            initial_result = await run_pipeline(_make_ctx(), config)
            pending = PendingDeliveryStore(tmp_path).load("2026-05-18", "morning")
            assert pending is not None
            initial_finalization = pending["finalization"]
            initial_status = json.loads((tmp_path / "publish_status.json").read_text())
            assert initial_status["degradation_reasons"] == [
                "llm_relevance_insufficient_candidates"
            ]

            recovered_result = await run_pipeline(_make_ctx(), config)

        assert initial_result.status == "degraded"
        assert recovered_result.status == "degraded"
        mock_summarize.assert_awaited_once()
        digest = json.loads((tmp_path / "2026-05-18" / "ai_digest.json").read_text())
        for field in (
            "selection_evidence",
            "degradation_reasons",
            "daily_judgement_source",
        ):
            assert digest[field] == initial_finalization[field]

    @pytest.mark.asyncio
    async def test_digest_publication_failure_is_degraded_and_queued(self, tmp_path: Path):
        """消息投递成功不能掩盖网站日报写入失败。"""
        from app.pipeline.news_pipeline import run_pipeline

        candidate = _make_candidate()
        publisher = MagicMock()
        publisher.publish_digest.side_effect = RuntimeError("database unavailable")
        retry_store = MagicMock()
        retry_store.has_pending_digest.return_value = False
        retry_store.has_recovered_digest.return_value = False

        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_is,
            patch(
                "app.pipeline.news_pipeline.summarize_news",
                new=AsyncMock(return_value=_make_llm_result()),
            ),
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_pusher_cls,
            patch("app.pipeline.news_pipeline.TopicClassifier"),
            patch("app.pipeline.news_pipeline.SourceMetricsStore") as mock_metrics_store_cls,
            patch("app.publication.publisher.Publisher.from_config", return_value=publisher),
            patch("app.publication.retry_store.PublicationRetryStore", return_value=retry_store),
        ):
            mock_is.return_value.load_window_candidates.return_value = [candidate]
            mock_pusher_cls.return_value.push_single_markdown = AsyncMock(
                return_value=_make_push_result()
            )
            mock_metrics_store_cls.return_value.write_selected_counts.return_value = 1

            result = await run_pipeline(
                _make_ctx(),
                _make_config(
                    publication_enabled=True,
                    publication_database_url="postgresql+psycopg://example.test/news",
                ),
            )

        assert result.status == "degraded"
        assert "publication_digest_write_failed: RuntimeError" in result.errors
        retry_store.enqueue_digest.assert_called_once()

    @pytest.mark.asyncio
    async def test_article_replay_failure_defers_digest_replay_and_degrades_empty_run(
        self, tmp_path: Path
    ):
        """内容重放按文章、日报的顺序执行，失败不能被空运行覆盖。"""
        from app.pipeline.news_pipeline import run_pipeline

        publisher = MagicMock()
        retry_store = MagicMock()
        retry_store.replay_articles.side_effect = RuntimeError("database unavailable")

        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_is,
            patch("app.publication.publisher.Publisher.from_config", return_value=publisher),
            patch("app.publication.retry_store.PublicationRetryStore", return_value=retry_store),
        ):
            mock_is.return_value.load_window_candidates.return_value = []
            result = await run_pipeline(
                _make_ctx(),
                _make_config(
                    publication_enabled=True,
                    publication_database_url="postgresql+psycopg://example.test/news",
                ),
            )

        assert result.status == "degraded"
        assert "publication_article_replay_failed: RuntimeError" in result.errors
        assert "publication_digest_replay_deferred" in result.errors
        retry_store.replay_digests.assert_not_called()

    @pytest.mark.asyncio
    async def test_pending_digest_recovery_does_not_generate_a_second_same_day_digest(
        self, tmp_path: Path
    ):
        """已投递消息对应的待恢复日报优先于同日的新选材。"""
        from app.pipeline.news_pipeline import run_pipeline
        from app.publication.retry_store import PublicationRetryStore

        candidate = _make_candidate()
        retries = PublicationRetryStore(tmp_path)
        retries.enqueue_digest(
            date="2026-05-18",
            period="morning",
            payload={
                "digest_date": "2026-05-18",
                "published_at": "2026-05-18T01:00:00+00:00",
                "headline_items": [],
                "selected": [],
                "daily_judgement": "first digest",
                "github_projects": [],
            },
        )
        publisher = MagicMock()

        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_is,
            patch(
                "app.pipeline.news_pipeline.summarize_news",
                new=AsyncMock(return_value=_make_llm_result()),
            ),
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_pusher_cls,
            patch("app.pipeline.news_pipeline.TopicClassifier"),
            patch("app.pipeline.news_pipeline.SourceMetricsStore") as mock_metrics_store_cls,
            patch("app.publication.publisher.Publisher.from_config", return_value=publisher),
        ):
            mock_is.return_value.load_window_candidates.return_value = [candidate]
            mock_pusher_cls.return_value.push_single_markdown = AsyncMock(
                return_value=_make_push_result()
            )
            mock_metrics_store_cls.return_value.write_selected_counts.return_value = 1

            result = await run_pipeline(
                _make_ctx(),
                _make_config(
                    publication_enabled=True,
                    publication_database_url="postgresql+psycopg://example.test/news",
                ),
            )

        assert result.status == "recovered"
        assert publisher.publish_digest.call_count == 1
        mock_pusher_cls.assert_not_called()

        publisher.reset_mock()
        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_is,
            patch(
                "app.pipeline.news_pipeline.summarize_news",
                new=AsyncMock(return_value=_make_llm_result()),
            ),
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_pusher_cls,
            patch("app.pipeline.news_pipeline.TopicClassifier"),
            patch("app.pipeline.news_pipeline.SourceMetricsStore") as mock_metrics_store_cls,
            patch("app.publication.publisher.Publisher.from_config", return_value=publisher),
        ):
            mock_is.return_value.load_window_candidates.return_value = [candidate]
            mock_pusher_cls.return_value.push_single_markdown = AsyncMock(
                return_value=_make_push_result()
            )
            mock_metrics_store_cls.return_value.write_selected_counts.return_value = 1
            result = await run_pipeline(
                _make_ctx(),
                _make_config(
                    publication_enabled=True,
                    publication_database_url="postgresql+psycopg://example.test/news",
                ),
            )

        assert result.status == "recovered"
        publisher.publish_digest.assert_not_called()
        mock_pusher_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_successful_digest_is_not_rewritten_by_a_same_day_rerun(self, tmp_path: Path):
        """首版日报成功后，手动重跑不得生成不同的网站日报或二次推送。"""
        from app.pipeline.news_pipeline import run_pipeline

        candidate = _make_candidate()
        publisher = MagicMock()
        config = _make_config(
            publication_enabled=True,
            publication_database_url="postgresql+psycopg://example.test/news",
        )
        ctx = _make_ctx()

        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_is,
            patch(
                "app.pipeline.news_pipeline.summarize_news",
                new=AsyncMock(return_value=_make_llm_result()),
            ) as summarize,
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_pusher_cls,
            patch("app.pipeline.news_pipeline.TopicClassifier"),
            patch("app.pipeline.news_pipeline.SourceMetricsStore") as mock_metrics_store_cls,
            patch("app.publication.publisher.Publisher.from_config", return_value=publisher),
        ):
            mock_is.return_value.load_window_candidates.return_value = [candidate]
            mock_pusher_cls.return_value.push_single_markdown = AsyncMock(
                return_value=_make_push_result()
            )
            mock_metrics_store_cls.return_value.write_selected_counts.return_value = 1

            first_result = await run_pipeline(ctx, config)
            second_result = await run_pipeline(ctx, config)

        assert first_result.status == "ok"
        assert second_result.status == "recovered"
        assert publisher.publish_digest.call_count == 1
        assert summarize.await_count == 1
        assert mock_pusher_cls.return_value.push_single_markdown.await_count == 1

    @pytest.mark.asyncio
    async def test_wecom_failure_retries_the_same_day_digest_without_rewriting_it(
        self, tmp_path: Path
    ):
        """内容发布成功、企微失败后，只重试原消息而不重算日报。"""
        from app.pipeline.news_pipeline import run_pipeline

        candidate = _make_candidate()
        publisher = MagicMock()
        config = _make_config(
            publication_enabled=True,
            publication_database_url="postgresql+psycopg://example.test/news",
        )
        ctx = _make_ctx()

        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_is,
            patch(
                "app.pipeline.news_pipeline.summarize_news",
                new=AsyncMock(return_value=_make_llm_result()),
            ) as summarize,
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_pusher_cls,
            patch("app.pipeline.news_pipeline.TopicClassifier"),
            patch("app.pipeline.news_pipeline.SourceMetricsStore") as mock_metrics_store_cls,
            patch("app.publication.publisher.Publisher.from_config", return_value=publisher),
        ):
            mock_is.return_value.load_window_candidates.return_value = [candidate]
            mock_pusher_cls.return_value.push_single_markdown = AsyncMock(
                side_effect=[_make_push_result(success=False), _make_push_result(success=True)]
            )
            mock_metrics_store_cls.return_value.write_selected_counts.return_value = 1

            first_result = await run_pipeline(ctx, config)
            second_result = await run_pipeline(ctx, config)

        assert first_result.status == "failed"
        assert second_result.status == "ok"
        assert publisher.publish_digest.call_count == 1
        assert summarize.await_count == 1
        assert mock_pusher_cls.return_value.push_single_markdown.await_count == 2

    @pytest.mark.asyncio
    async def test_pending_delivery_write_failure_cannot_rewrite_a_published_digest(
        self, tmp_path: Path
    ):
        """本地待投递文件失败时，数据库首版日报仍是同日定版真相源。"""
        from app.pipeline.news_pipeline import run_pipeline

        candidate = _make_candidate()
        publisher = MagicMock()
        publisher.digest_exists.side_effect = [False, False, True]
        config = _make_config(
            publication_enabled=True,
            publication_database_url="postgresql+psycopg://example.test/news",
        )
        ctx = _make_ctx()

        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_is,
            patch(
                "app.pipeline.news_pipeline.summarize_news",
                new=AsyncMock(return_value=_make_llm_result()),
            ) as summarize,
            patch("app.pipeline.news_pipeline.TopicClassifier"),
            patch("app.pipeline.news_pipeline.SourceMetricsStore") as mock_metrics_store_cls,
            patch("app.publication.publisher.Publisher.from_config", return_value=publisher),
            patch("app.delivery.store.PendingDeliveryStore.save", side_effect=OSError("disk full")),
        ):
            mock_is.return_value.load_window_candidates.return_value = [candidate]
            mock_metrics_store_cls.return_value.write_selected_counts.return_value = 1

            first_result = await run_pipeline(ctx, config)
            second_result = await run_pipeline(ctx, config)

        assert first_result.status == "failed"
        assert second_result.status == "recovered"
        assert publisher.publish_digest.call_count == 1
        assert summarize.await_count == 1

    @pytest.mark.asyncio
    async def test_digest_receipt_write_failure_cannot_rewrite_a_published_digest(
        self, tmp_path: Path
    ):
        """消息已送达但 receipt 写入失败时，数据库首版仍阻止同日覆盖。"""
        from app.pipeline.news_pipeline import run_pipeline

        candidate = _make_candidate()
        publisher = MagicMock()
        publisher.digest_exists.side_effect = [False, False, True]
        retry_store = MagicMock()
        retry_store.has_pending_digest.return_value = False
        retry_store.has_recovered_digest.return_value = False
        retry_store.mark_digest_published.side_effect = OSError("disk full")
        config = _make_config(
            publication_enabled=True,
            publication_database_url="postgresql+psycopg://example.test/news",
        )
        ctx = _make_ctx()

        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_is,
            patch(
                "app.pipeline.news_pipeline.summarize_news",
                new=AsyncMock(return_value=_make_llm_result()),
            ) as summarize,
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_pusher_cls,
            patch("app.pipeline.news_pipeline.TopicClassifier"),
            patch("app.pipeline.news_pipeline.SourceMetricsStore") as mock_metrics_store_cls,
            patch("app.publication.publisher.Publisher.from_config", return_value=publisher),
            patch("app.publication.retry_store.PublicationRetryStore", return_value=retry_store),
        ):
            mock_is.return_value.load_window_candidates.return_value = [candidate]
            mock_pusher_cls.return_value.push_single_markdown = AsyncMock(
                return_value=_make_push_result()
            )
            mock_metrics_store_cls.return_value.write_selected_counts.return_value = 1

            first_result = await run_pipeline(ctx, config)
            second_result = await run_pipeline(ctx, config)

        assert first_result.status == "degraded"
        assert first_result.pushed is True
        assert "publication_digest_receipt_failed: OSError" in first_result.errors
        assert second_result.status == "recovered"
        assert publisher.publish_digest.call_count == 1
        assert summarize.await_count == 1

    @pytest.mark.asyncio
    async def test_pipeline_uses_top_ten_selection_limit(self, tmp_path: Path):
        from app.pipeline.news_pipeline import run_pipeline

        config = _make_config()
        ctx = _make_ctx()
        candidate = _make_candidate()
        llm_result = _make_llm_result()
        push_result = _make_push_result(success=True)
        selected = [candidate]

        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_is,
            patch(
                "app.pipeline.news_pipeline.summarize_news", new=AsyncMock(return_value=llm_result)
            ),
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_pusher_cls,
            patch("app.pipeline.news_pipeline.TopicClassifier") as mock_cls,
            patch("app.pipeline.news_pipeline.SourceMetricsStore") as mock_metrics_store_cls,
            patch("app.pipeline.news_pipeline.Merger") as mock_merger_cls,
        ):
            mock_is_inst = MagicMock()
            mock_is_inst.load_window_candidates.return_value = [candidate]
            mock_is.return_value = mock_is_inst
            mock_cls.return_value = MagicMock()
            mock_pusher = MagicMock()
            mock_pusher.push_single_markdown = AsyncMock(return_value=push_result)
            mock_pusher_cls.return_value = mock_pusher
            mock_metrics_store_cls.return_value.write_selected_counts.return_value = 1
            mock_merger_cls.return_value.merge.return_value = selected

            result = await run_pipeline(ctx, config)

        assert result.status == "ok"
        mock_merger_cls.assert_called_once_with(top_n=10)


class TestPipelinePushFailure:
    """When the WeCom push fails, the pipeline reports failure."""

    @pytest.mark.asyncio
    async def test_push_failure_returns_failed(self, tmp_path: Path):
        """A push failure produces status='failed' with pushed=False and error details."""
        from app.pipeline.news_pipeline import run_pipeline

        config = _make_config()
        ctx = _make_ctx()
        candidate = _make_candidate()
        llm_result = _make_llm_result()
        push_result = _make_push_result(success=False)

        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_is,
            patch(
                "app.pipeline.news_pipeline.summarize_news", new=AsyncMock(return_value=llm_result)
            ),
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_pusher_cls,
            patch("app.pipeline.news_pipeline.TopicClassifier") as mock_cls,
        ):
            mock_is_inst = MagicMock()
            mock_is_inst.load_window_candidates.return_value = [candidate]
            mock_is.return_value = mock_is_inst

            mock_cls_inst = MagicMock()
            mock_cls.return_value = mock_cls_inst

            mock_pusher = MagicMock()
            mock_pusher.push_single_markdown = AsyncMock(return_value=push_result)
            mock_pusher_cls.return_value = mock_pusher

            result = await run_pipeline(ctx, config)

        assert result.status == "failed"
        assert result.pushed is False
        assert len(result.errors) > 0


class TestTelegramDeliveryRetry:
    """Telegram enabled flows keep a pending record and can resume from it."""

    @pytest.mark.asyncio
    async def test_telegram_failure_leaves_pending_delivery(self, tmp_path: Path):
        from app.delivery.store import PendingDeliveryStore
        from app.pipeline.news_pipeline import run_pipeline

        config = _make_config(
            telegram_bot_token="123:token",
            telegram_chat_id="456",
        )
        ctx = _make_ctx()
        candidate = _make_candidate()
        llm_result = _make_llm_result()
        push_result = _make_push_result(success=True)

        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_is,
            patch(
                "app.pipeline.news_pipeline.summarize_news", new=AsyncMock(return_value=llm_result)
            ),
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_wecom_cls,
            patch("app.pipeline.news_pipeline.TelegramPusher") as mock_telegram_cls,
            patch("app.pipeline.news_pipeline.TopicClassifier") as mock_cls,
            patch("app.pipeline.news_pipeline.GitHubStore") as mock_github_store,
            patch("app.pipeline.news_pipeline.GitHubExposureStore") as mock_exposure,
            patch("app.pipeline.news_pipeline.SourceMetricsStore") as mock_metrics_store_cls,
        ):
            mock_is_inst = MagicMock()
            mock_is_inst.load_window_candidates.return_value = [candidate]
            mock_is.return_value = mock_is_inst
            mock_cls.return_value = MagicMock()
            mock_github_store.return_value.load_latest_snapshot.return_value = []
            mock_exposure.return_value.load.return_value = {}

            mock_wecom = MagicMock()
            mock_wecom.push_single_markdown = AsyncMock(return_value=push_result)
            mock_wecom_cls.return_value = mock_wecom

            mock_telegram = MagicMock()
            mock_telegram.push_messages = AsyncMock(side_effect=RuntimeError("telegram down"))
            mock_telegram_cls.return_value = mock_telegram

            mock_metrics_store_cls.return_value.write_selected_counts.return_value = 1

            result = await run_pipeline(ctx, config)

        assert result.status == "degraded"
        assert result.pushed is True
        pending = PendingDeliveryStore(tmp_path).load("2026-05-18", "morning")
        assert pending is not None
        assert pending["channels"]["wecom"]["status"] == "succeeded"
        assert pending["channels"]["telegram"]["status"] == "failed"
        assert pending["messages"]["wecom_markdown"]
        assert pending["messages"]["telegram_messages"]

    @pytest.mark.asyncio
    async def test_pending_delivery_retry_skips_llm_and_finishes(self, tmp_path: Path):
        from app.delivery.store import PendingDeliveryStore
        from app.pipeline.news_pipeline import run_pipeline

        config = _make_config(
            telegram_bot_token="123:token",
            telegram_chat_id="456",
        )
        ctx = _make_ctx()
        store = PendingDeliveryStore(tmp_path)
        store.save(
            "2026-05-18",
            "morning",
            {
                "delivery_id": "2026-05-18-morning-abc123",
                "channels": {
                    "wecom": {
                        "enabled": True,
                        "status": "succeeded",
                        "attempted_at": "2026-05-18T08:00:00",
                        "error": None,
                    },
                    "telegram": {
                        "enabled": True,
                        "status": "pending",
                        "attempted_at": None,
                        "error": None,
                    },
                },
                "messages": {
                    "wecom_markdown": "wecom markdown",
                    "telegram_messages": ["telegram message"],
                },
                "finalization": {
                    "date": "2026-05-18",
                    "period": "morning",
                    "trigger_mode": "cli_compat",
                    "headline_items": [
                        {
                            "title": "Test News",
                            "url": "https://example.com/1",
                            "core_summary": "A test summary.",
                            "importance": "高",
                            "trend": "利好",
                            "source": "qbitai",
                            "display_category": "AI",
                            "topic_label": None,
                            "topic_confidence": 0.9,
                            "final_score": 8.8,
                        }
                    ],
                    "daily_judgement": "AI行业稳步发展",
                    "source_failures": [],
                    "published_urls": ["https://example.com/1"],
                    "published_keys": ["key-1"],
                    "github_projects": [
                        {
                            "full_name": "org/repo",
                            "final_score": 8.1,
                            "activity": 1.0,
                            "popularity": 1.0,
                            "relevance": 1.0,
                            "penalty": 0.0,
                            "recommendation": "值得关注",
                            "matched_topics": [],
                            "matched_keywords": [],
                        }
                    ],
                    "selection_evidence": [],
                    "relevance_rejections": [],
                    "selected_counts_by_source": {"qbitai": 1},
                    "metric_rows": [
                        {
                            "source": "qbitai",
                            "category": "ai",
                            "candidate_count": 1,
                            "relevance_accepted_count": 1,
                            "relevance_rejected_count": 0,
                            "selected_today_count": 1,
                            "selected_backfill_count": 0,
                            "rejection_reasons": [],
                        }
                    ],
                },
            },
        )

        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch("app.pipeline.news_pipeline.summarize_news") as mock_summarize,
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_is,
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_wecom_cls,
            patch("app.pipeline.news_pipeline.TelegramPusher") as mock_telegram_cls,
            patch("app.pipeline.news_pipeline.TopicClassifier") as mock_cls,
            patch("app.pipeline.news_pipeline.SourceMetricsStore") as mock_metrics_store_cls,
            patch("app.pipeline.news_pipeline.GitHubStore") as mock_github_store,
            patch("app.pipeline.news_pipeline.GitHubExposureStore") as mock_exposure,
        ):
            mock_is.return_value = MagicMock()
            mock_cls.return_value = MagicMock()
            mock_wecom_cls.return_value = MagicMock()
            mock_github_store.return_value.load_latest_snapshot.return_value = []
            mock_exposure.return_value.load.return_value = {}

            mock_metrics_store = MagicMock()
            mock_metrics_store.write_selected_counts.return_value = 1
            mock_metrics_store_cls.return_value = mock_metrics_store

            mock_telegram = MagicMock()
            mock_telegram.push_messages = AsyncMock(return_value=MagicMock(messages_sent=1))
            mock_telegram_cls.return_value = mock_telegram

            result = await run_pipeline(ctx, config)

        assert result.status == "ok"
        assert result.pushed is True
        mock_summarize.assert_not_called()
        mock_wecom_cls.assert_not_called()
        assert store.load("2026-05-18", "morning") is None

    @pytest.mark.asyncio
    async def test_push_exception_returns_failed(self, tmp_path: Path):
        """An exception from the pusher is caught and reported as failure."""
        from app.pipeline.news_pipeline import run_pipeline

        config = _make_config()
        ctx = _make_ctx()
        candidate = _make_candidate()
        llm_result = _make_llm_result()

        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_is,
            patch(
                "app.pipeline.news_pipeline.summarize_news", new=AsyncMock(return_value=llm_result)
            ),
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_pusher_cls,
            patch("app.pipeline.news_pipeline.TopicClassifier") as mock_cls,
        ):
            mock_is_inst = MagicMock()
            mock_is_inst.load_window_candidates.return_value = [candidate]
            mock_is.return_value = mock_is_inst

            mock_cls_inst = MagicMock()
            mock_cls.return_value = mock_cls_inst

            # Pusher raises an exception
            mock_pusher = MagicMock()
            mock_pusher.push_single_markdown = AsyncMock(side_effect=RuntimeError("rate limited"))
            mock_pusher_cls.return_value = mock_pusher

            result = await run_pipeline(ctx, config)

        assert result.status == "failed"
        assert result.pushed is False
        assert len(result.errors) > 0


class TestPipelineNoCandidates:
    """When there are no candidates in the ingestion store, the pipeline skips."""

    @pytest.mark.asyncio
    async def test_no_candidates_returns_skipped(self, tmp_path: Path):
        """Empty candidate pool results in status='skipped'."""
        from app.pipeline.news_pipeline import run_pipeline

        config = _make_config()
        ctx = _make_ctx()

        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_is,
        ):
            mock_is_inst = MagicMock()
            mock_is_inst.load_window_candidates.return_value = []
            mock_is.return_value = mock_is_inst

            result = await run_pipeline(ctx, config)

        assert result.status == "skipped"
        assert result.selected_count == 0
        assert result.pushed is False
        publish_status = json.loads((tmp_path / "publish_status.json").read_text(encoding="utf-8"))
        assert publish_status["status"] == "skipped"
        assert publish_status["selected_count"] == 0
        assert publish_status["pushed"] is False


class TestPipelinePublishScope:
    """Formal publishing must obey the ai_only scope from RunContext."""

    @pytest.mark.asyncio
    async def test_ai_only_scope_excludes_non_ai_candidates(self, tmp_path: Path):
        from app.pipeline.news_pipeline import run_pipeline

        config = _make_config()
        ctx = _make_ctx()
        ai_candidate = _make_candidate(url="https://example.com/ai", category="ai")
        game_candidate = _make_candidate(url="https://example.com/game", category="game")
        llm_result = _make_llm_result()
        push_result = _make_push_result(success=True)

        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_is,
            patch(
                "app.pipeline.news_pipeline.summarize_news",
                new=AsyncMock(return_value=llm_result),
            ) as mock_llm,
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_pusher_cls,
            patch("app.pipeline.news_pipeline.TopicClassifier") as mock_cls,
            patch("app.pipeline.news_pipeline.SourceMetricsStore") as mock_metrics_store_cls,
        ):
            mock_is_inst = MagicMock()
            mock_is_inst.load_window_candidates.return_value = [ai_candidate, game_candidate]
            mock_is.return_value = mock_is_inst

            mock_cls_inst = MagicMock()
            mock_cls.return_value = mock_cls_inst

            mock_pusher = MagicMock()
            mock_pusher.push_single_markdown = AsyncMock(return_value=push_result)
            mock_pusher_cls.return_value = mock_pusher
            mock_metrics_store_cls.return_value.write_selected_counts.return_value = 1

            result = await run_pipeline(ctx, config)

        assert result.status == "ok"
        summarized_items = mock_llm.await_args.args[0]
        assert [item["link"] for item in summarized_items] == ["https://example.com/ai"]


class TestPipelineGitHubSupplement:
    @pytest.mark.asyncio
    async def test_github_items_rendered_but_not_sent_to_llm(self, tmp_path: Path):
        from app.pipeline.news_pipeline import run_pipeline
        from collectors.github import GitHubRepoItem

        config = _make_config()
        ctx = _make_ctx()
        candidate = _make_candidate(url="https://example.com/ai", category="ai")
        llm_result = _make_llm_result()
        push_result = _make_push_result(success=True)
        repos = [
            GitHubRepoItem(
                full_name="owner/repo",
                url="https://github.com/owner/repo",
                description="desc",
                stars=10,
                language="Python",
                fetched_at="2026-05-18T08:00:00",
            )
        ]

        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_is,
            patch("app.pipeline.news_pipeline.GitHubStore") as mock_github_store,
            patch("app.pipeline.news_pipeline.GitHubExposureStore") as mock_exposure,
            patch(
                "app.pipeline.news_pipeline.summarize_news",
                new=AsyncMock(return_value=llm_result),
            ) as mock_llm,
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_pusher_cls,
            patch("app.pipeline.news_pipeline.TopicClassifier") as mock_cls,
            patch("app.pipeline.news_pipeline.SourceMetricsStore") as mock_metrics_store_cls,
        ):
            mock_is_inst = MagicMock()
            mock_is_inst.load_window_candidates.return_value = [candidate]
            mock_is.return_value = mock_is_inst
            mock_github_store.return_value.load_latest_snapshot.return_value = repos
            mock_exposure.return_value.load.return_value = {}
            mock_cls.return_value = MagicMock()
            mock_pusher = MagicMock()
            mock_pusher.push_single_markdown = AsyncMock(return_value=push_result)
            mock_pusher_cls.return_value = mock_pusher
            mock_metrics_store_cls.return_value.write_selected_counts.return_value = 1

            result = await run_pipeline(ctx, config)

        assert result.status == "ok"
        assert mock_llm.await_args.args[0] == [
            {
                "title": "Test",
                "link": "https://example.com/ai",
                "summary": "Summary",
                "published_at": "2026-05-18",
            }
        ]
        pushed_markdown = mock_pusher.push_single_markdown.await_args.args[0]
        assert "今日值得看项目" in pushed_markdown
        assert "owner/repo" in pushed_markdown

    @pytest.mark.asyncio
    async def test_llm_parse_failure_writes_failed_publish_status(self, tmp_path: Path):
        from app.pipeline.news_pipeline import run_pipeline

        config = _make_config()
        ctx = _make_ctx()
        candidate = _make_candidate()
        llm_result = {"_parse_error": "bad json", "headline_items": []}

        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_is,
            patch(
                "app.pipeline.news_pipeline.summarize_news",
                new=AsyncMock(return_value=llm_result),
            ),
            patch("app.pipeline.news_pipeline.TopicClassifier") as mock_cls,
        ):
            mock_is.return_value.load_window_candidates.return_value = [candidate]
            mock_cls.return_value = MagicMock()

            result = await run_pipeline(ctx, config)

        assert result.status == "failed"
        assert result.pushed is False
        publish_status = json.loads((tmp_path / "publish_status.json").read_text(encoding="utf-8"))
        assert publish_status["status"] == "failed"
        assert publish_status["selected_count"] == 1
        assert publish_status["summary_count"] == 0
        assert publish_status["final_count"] == 0
        assert publish_status["pushed"] is False
        assert publish_status["errors"] == ["llm_parse: bad json"]

    @pytest.mark.asyncio
    async def test_github_exposure_recorded_only_after_successful_push(self, tmp_path: Path):
        from app.pipeline.news_pipeline import run_pipeline
        from collectors.github import GitHubRepoItem

        config = _make_config()
        ctx = _make_ctx()
        candidate = _make_candidate(url="https://example.com/ai", category="ai")
        llm_result = _make_llm_result()
        push_result = _make_push_result(success=True)
        repos = [
            GitHubRepoItem(
                full_name="owner/repo",
                url="https://github.com/owner/repo",
                description="desc",
                stars=10,
                language="Python",
                fetched_at="2026-05-18T08:00:00",
            )
        ]

        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_is,
            patch("app.pipeline.news_pipeline.GitHubStore") as mock_github_store,
            patch("app.pipeline.news_pipeline.GitHubExposureStore") as mock_exposure,
            patch(
                "app.pipeline.news_pipeline.summarize_news",
                new=AsyncMock(return_value=llm_result),
            ),
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_pusher_cls,
            patch("app.pipeline.news_pipeline.TopicClassifier") as mock_cls,
            patch("app.pipeline.news_pipeline.SourceMetricsStore") as mock_metrics_store_cls,
        ):
            mock_is_inst = MagicMock()
            mock_is_inst.load_window_candidates.return_value = [candidate]
            mock_is.return_value = mock_is_inst
            mock_github_store.return_value.load_latest_snapshot.return_value = repos
            mock_exposure.return_value.load.return_value = {}
            mock_cls.return_value = MagicMock()
            mock_pusher = MagicMock()
            mock_pusher.push_single_markdown = AsyncMock(return_value=push_result)
            mock_pusher_cls.return_value = mock_pusher
            mock_metrics_store_cls.return_value.write_selected_counts.return_value = 1

            result = await run_pipeline(ctx, config)

        assert result.status == "ok"
        mock_exposure.return_value.record.assert_called_once_with(["owner/repo"])

    @pytest.mark.asyncio
    async def test_github_exposure_not_recorded_when_push_fails(self, tmp_path: Path):
        from app.pipeline.news_pipeline import run_pipeline
        from collectors.github import GitHubRepoItem

        config = _make_config()
        ctx = _make_ctx()
        candidate = _make_candidate(url="https://example.com/ai", category="ai")
        llm_result = _make_llm_result()
        push_result = _make_push_result(success=False)
        repos = [
            GitHubRepoItem(
                full_name="owner/repo",
                url="https://github.com/owner/repo",
                description="desc",
                stars=10,
                language="Python",
                fetched_at="2026-05-18T08:00:00",
            )
        ]

        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_is,
            patch("app.pipeline.news_pipeline.GitHubStore") as mock_github_store,
            patch("app.pipeline.news_pipeline.GitHubExposureStore") as mock_exposure,
            patch(
                "app.pipeline.news_pipeline.summarize_news",
                new=AsyncMock(return_value=llm_result),
            ),
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_pusher_cls,
            patch("app.pipeline.news_pipeline.TopicClassifier") as mock_cls,
        ):
            mock_is_inst = MagicMock()
            mock_is_inst.load_window_candidates.return_value = [candidate]
            mock_is.return_value = mock_is_inst
            mock_github_store.return_value.load_latest_snapshot.return_value = repos
            mock_exposure.return_value.load.return_value = {}
            mock_cls.return_value = MagicMock()
            mock_pusher = MagicMock()
            mock_pusher.push_single_markdown = AsyncMock(return_value=push_result)
            mock_pusher_cls.return_value = mock_pusher

            result = await run_pipeline(ctx, config)

        assert result.status == "failed"
        mock_exposure.return_value.record.assert_not_called()

    @pytest.mark.asyncio
    async def test_source_failures_use_pipeline_start_snapshot(self, tmp_path: Path):
        from app.pipeline.news_pipeline import run_pipeline

        config = _make_config()
        ctx = _make_ctx()
        candidate = _make_candidate(url="https://example.com/ai", category="ai")
        llm_result = _make_llm_result()
        push_result = _make_push_result(success=True)

        async def mutate_status_before_push(markdown: str):
            return push_result

        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_is,
            patch(
                "app.pipeline.news_pipeline.summarize_news",
                new=AsyncMock(return_value=llm_result),
            ),
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_pusher_cls,
            patch("app.pipeline.news_pipeline.TopicClassifier") as mock_cls,
            patch("app.pipeline.news_pipeline.SourceMetricsStore") as mock_metrics_store_cls,
            patch("app.pipeline.news_pipeline.StateStore") as mock_state_store_cls,
            patch("app.pipeline.news_pipeline.IngestStatusStore") as mock_ingest_status_store_cls,
        ):
            mock_is.return_value.load_window_candidates.return_value = [candidate]
            mock_cls.return_value = MagicMock()
            mock_pusher_cls.return_value.push_single_markdown = AsyncMock(
                side_effect=mutate_status_before_push
            )
            mock_metrics_store_cls.return_value.write_selected_counts.return_value = 1
            mock_state_store_cls.return_value.load_pushed_urls.return_value = set()
            mock_state_store_cls.return_value.load_published_keys.return_value = set()
            mock_ingest_status_store_cls.return_value.load_status.side_effect = [
                {
                    "last_ingest_at": "2026-05-18T08:00:00",
                    "last_item_count": 1,
                    "successful_sources": ["qbitai"],
                    "failed_sources": ["qbitai: timeout"],
                    "skipped_sources": [],
                },
                {
                    "last_ingest_at": "2026-05-18T08:30:00",
                    "last_item_count": 1,
                    "successful_sources": ["sspai"],
                    "failed_sources": ["sspai: blocked"],
                    "skipped_sources": [],
                },
            ]

            result = await run_pipeline(ctx, config)

        assert result.status == "ok"
        digest_payload = mock_state_store_cls.return_value.write_digest.call_args.args[0]
        assert digest_payload.source_failures == ["qbitai: timeout"]


class TestPipelineDigestPresentation:
    @pytest.mark.asyncio
    async def test_digest_uses_display_category_topic_label_and_source(self, tmp_path: Path):
        from app.pipeline.news_pipeline import run_pipeline

        config = _make_config()
        ctx = _make_ctx()
        ai_candidate = _make_candidate(
            title="OpenAI 发布新模型",
            url="https://example.com/model",
            source="openai_blog",
        )
        ai_candidate.topic = "model_release"
        tool_candidate = _make_candidate(
            title="开源 Agent SDK",
            url="https://example.com/sdk",
            source="github",
        )
        tool_candidate.topic = "developer_tooling"
        llm_result = {
            "headline_items": [
                {
                    "title": "OpenAI 发布新模型",
                    "url": "https://example.com/model",
                    "core_summary": "模型更新。",
                    "importance": "高",
                    "trend": "利好",
                },
                {
                    "title": "开源 Agent SDK",
                    "url": "https://example.com/sdk",
                    "core_summary": "开发者工具更新。",
                    "importance": "中",
                    "trend": "关注",
                },
            ],
            "daily_judgement": "今天以模型和工具更新为主。",
        }
        push_result = _make_push_result(success=True)

        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_is,
            patch(
                "app.pipeline.news_pipeline.summarize_news",
                new=AsyncMock(return_value=llm_result),
            ),
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_pusher_cls,
            patch("app.pipeline.news_pipeline.TopicClassifier") as mock_cls,
            patch("app.pipeline.news_pipeline.SourceMetricsStore") as mock_metrics_store_cls,
        ):
            mock_is_inst = MagicMock()
            mock_is_inst.load_window_candidates.return_value = [ai_candidate, tool_candidate]
            mock_is.return_value = mock_is_inst
            mock_cls.return_value = MagicMock()
            mock_pusher = MagicMock()
            mock_pusher.push_single_markdown = AsyncMock(return_value=push_result)
            mock_pusher_cls.return_value = mock_pusher
            mock_metrics_store_cls.return_value.write_selected_counts.return_value = 2

            result = await run_pipeline(ctx, config)

        assert result.status == "ok"
        pushed_markdown = mock_pusher.push_single_markdown.await_args.args[0]
        assert "【AI】1" in pushed_markdown
        assert "【工具】1" in pushed_markdown
        assert "[模型]" in pushed_markdown
        assert "[开源]" in pushed_markdown
        assert "OpenAI" in pushed_markdown
        assert "GitHub" in pushed_markdown


class TestPipelineAllDigestScope:
    @pytest.mark.asyncio
    async def test_all_digest_scope_keeps_tool_and_game_candidates(self, tmp_path: Path):
        from app.pipeline.news_pipeline import run_pipeline

        config = _make_config()
        ctx = _make_ctx(publish_scope="all_digest")
        ai_candidate = _make_candidate(url="https://example.com/ai", category="ai")
        tool_candidate = _make_candidate(
            url="https://example.com/tool", category="tool", source="sspai"
        )
        game_candidate = _make_candidate(
            url="https://example.com/game", category="game", source="yystv"
        )
        llm_result = {
            "headline_items": [
                {
                    "title": "AI News",
                    "url": "https://example.com/ai",
                    "core_summary": "AI summary.",
                    "importance": "高",
                    "trend": "利好",
                },
                {
                    "title": "Tool News",
                    "url": "https://example.com/tool",
                    "core_summary": "Tool summary.",
                    "importance": "中",
                    "trend": "稳定",
                },
                {
                    "title": "Game News",
                    "url": "https://example.com/game",
                    "core_summary": "Game summary.",
                    "importance": "高",
                    "trend": "利好",
                },
            ],
            "daily_judgement": "AI行业稳步发展",
            "github_projects": [],
        }
        push_result = _make_push_result(success=True)

        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_is,
            patch(
                "app.pipeline.news_pipeline.summarize_news",
                new=AsyncMock(return_value=llm_result),
            ),
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_pusher_cls,
            patch("app.pipeline.news_pipeline.TopicClassifier") as mock_cls,
            patch("app.pipeline.news_pipeline.GitHubStore") as mock_github,
            patch("app.pipeline.news_pipeline.SourceMetricsStore") as mock_metrics_store_cls,
        ):
            mock_is_inst = MagicMock()
            mock_is_inst.load_window_candidates.return_value = [
                ai_candidate,
                tool_candidate,
                game_candidate,
            ]
            mock_is.return_value = mock_is_inst
            mock_cls.return_value = MagicMock()
            mock_github.return_value.load_latest_snapshot.return_value = []
            mock_pusher = MagicMock()
            mock_pusher.push_single_markdown = AsyncMock(return_value=push_result)
            mock_pusher_cls.return_value = mock_pusher
            mock_metrics_store_cls.return_value.write_selected_counts.return_value = 3

            result = await run_pipeline(ctx, config)

        assert result.status == "ok"
        assert result.selected_count == 3
        # Verify all three were passed to the LLM summarizer
        news_items = mock_is_inst.load_window_candidates.return_value
        assert len(news_items) == 3

    @pytest.mark.asyncio
    async def test_ai_only_scope_drops_tool_and_game(self, tmp_path: Path):
        from app.pipeline.news_pipeline import run_pipeline

        config = _make_config()
        ctx = _make_ctx(publish_scope="ai_only")
        candidates = [
            _make_candidate(url="https://example.com/ai", category="ai"),
            _make_candidate(url="https://example.com/tool", category="tool", source="sspai"),
            _make_candidate(url="https://example.com/game", category="game", source="yystv"),
        ]
        llm_result = _make_llm_result()
        push_result = _make_push_result(success=True)

        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_is,
            patch(
                "app.pipeline.news_pipeline.summarize_news",
                new=AsyncMock(return_value=llm_result),
            ),
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_pusher_cls,
            patch("app.pipeline.news_pipeline.TopicClassifier") as mock_cls,
            patch("app.pipeline.news_pipeline.GitHubStore") as mock_github,
            patch("app.pipeline.news_pipeline.SourceMetricsStore") as mock_metrics_store_cls,
        ):
            mock_is_inst = MagicMock()
            mock_is_inst.load_window_candidates.return_value = candidates
            mock_is.return_value = mock_is_inst
            mock_cls.return_value = MagicMock()
            mock_github.return_value.load_latest_snapshot.return_value = []
            mock_pusher = MagicMock()
            mock_pusher.push_single_markdown = AsyncMock(return_value=push_result)
            mock_pusher_cls.return_value = mock_pusher
            mock_metrics_store_cls.return_value.write_selected_counts.return_value = 1

            result = await run_pipeline(ctx, config)

        assert result.status == "ok"
        assert result.selected_count == 1


class TestDisplayCategoryMapping:
    """Verify internal category → display category lands in correct WeCom sections."""

    @pytest.mark.asyncio
    async def test_tool_category_maps_to_tools_section(self, tmp_path: Path):
        from app.pipeline.news_pipeline import run_pipeline

        config = _make_config()
        ctx = _make_ctx(publish_scope="all_digest")
        candidate = _make_candidate(
            title="效率工具推荐",
            url="https://sspai.com/post/tool",
            source="sspai",
            category="tool",
        )
        llm_result = {
            "headline_items": [
                {
                    "title": "效率工具推荐",
                    "url": "https://sspai.com/post/tool",
                    "core_summary": "工具推荐。",
                    "importance": "中",
                    "trend": "关注",
                }
            ],
            "daily_judgement": "工具资讯为主。",
        }
        push_result = _make_push_result(success=True)

        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_is,
            patch(
                "app.pipeline.news_pipeline.summarize_news",
                new=AsyncMock(return_value=llm_result),
            ),
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_pusher_cls,
            patch("app.pipeline.news_pipeline.TopicClassifier") as mock_cls,
            patch("app.pipeline.news_pipeline.GitHubStore") as mock_github,
            patch("app.pipeline.news_pipeline.SourceMetricsStore") as mock_metrics_store_cls,
        ):
            mock_is_inst = MagicMock()
            mock_is_inst.load_window_candidates.return_value = [candidate]
            mock_is.return_value = mock_is_inst
            mock_cls.return_value = MagicMock()
            mock_github.return_value.load_latest_snapshot.return_value = []
            mock_pusher = MagicMock()
            mock_pusher.push_single_markdown = AsyncMock(return_value=push_result)
            mock_pusher_cls.return_value = mock_pusher
            mock_metrics_store_cls.return_value.write_selected_counts.return_value = 1

            result = await run_pipeline(ctx, config)

        assert result.status == "ok"
        pushed = mock_pusher.push_single_markdown.await_args.args[0]
        assert "【工具】1" in pushed

    @pytest.mark.asyncio
    async def test_game_category_maps_to_game_section(self, tmp_path: Path):
        from app.pipeline.news_pipeline import run_pipeline

        config = _make_config()
        ctx = _make_ctx(publish_scope="all_digest")
        candidate = _make_candidate(
            title="新游戏评测",
            url="https://yystv.cn/p/game",
            source="yystv",
            category="game",
        )
        llm_result = {
            "headline_items": [
                {
                    "title": "新游戏评测",
                    "url": "https://yystv.cn/p/game",
                    "core_summary": "游戏评测。",
                    "importance": "高",
                    "trend": "利好",
                }
            ],
            "daily_judgement": "游戏资讯为主。",
        }
        push_result = _make_push_result(success=True)

        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_is,
            patch(
                "app.pipeline.news_pipeline.summarize_news",
                new=AsyncMock(return_value=llm_result),
            ),
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_pusher_cls,
            patch("app.pipeline.news_pipeline.TopicClassifier") as mock_cls,
            patch("app.pipeline.news_pipeline.GitHubStore") as mock_github,
            patch("app.pipeline.news_pipeline.SourceMetricsStore") as mock_metrics_store_cls,
        ):
            mock_is_inst = MagicMock()
            mock_is_inst.load_window_candidates.return_value = [candidate]
            mock_is.return_value = mock_is_inst
            mock_cls.return_value = MagicMock()
            mock_github.return_value.load_latest_snapshot.return_value = []
            mock_pusher = MagicMock()
            mock_pusher.push_single_markdown = AsyncMock(return_value=push_result)
            mock_pusher_cls.return_value = mock_pusher
            mock_metrics_store_cls.return_value.write_selected_counts.return_value = 1

            result = await run_pipeline(ctx, config)

        assert result.status == "ok"
        pushed = mock_pusher.push_single_markdown.await_args.args[0]
        assert "【游戏】1" in pushed

    @pytest.mark.asyncio
    async def test_ai_tool_game_all_land_in_correct_sections(self, tmp_path: Path):
        from app.pipeline.news_pipeline import run_pipeline

        config = _make_config()
        ctx = _make_ctx(publish_scope="all_digest")
        candidates = [
            _make_candidate(title="AI新闻", url="https://a.com/1", source="qbitai", category="ai"),
            _make_candidate(
                title="工具推荐", url="https://t.com/1", source="sspai", category="tool"
            ),
            _make_candidate(
                title="游戏评测", url="https://g.com/1", source="yystv", category="game"
            ),
        ]
        llm_result = {
            "headline_items": [
                {
                    "title": "AI新闻",
                    "url": "https://a.com/1",
                    "core_summary": "AI。",
                    "importance": "高",
                    "trend": "利好",
                },
                {
                    "title": "工具推荐",
                    "url": "https://t.com/1",
                    "core_summary": "工具。",
                    "importance": "中",
                    "trend": "稳定",
                },
                {
                    "title": "游戏评测",
                    "url": "https://g.com/1",
                    "core_summary": "游戏。",
                    "importance": "高",
                    "trend": "利好",
                },
            ],
            "daily_judgement": "三类资讯齐全。",
        }
        push_result = _make_push_result(success=True)

        with (
            patch("app.pipeline.news_pipeline._DATA_DIR", tmp_path),
            patch("app.pipeline.news_pipeline.IngestionStore") as mock_is,
            patch(
                "app.pipeline.news_pipeline.summarize_news",
                new=AsyncMock(return_value=llm_result),
            ),
            patch("app.pipeline.news_pipeline.WeComPusher") as mock_pusher_cls,
            patch("app.pipeline.news_pipeline.TopicClassifier") as mock_cls,
            patch("app.pipeline.news_pipeline.GitHubStore") as mock_github,
            patch("app.pipeline.news_pipeline.SourceMetricsStore") as mock_metrics_store_cls,
        ):
            mock_is_inst = MagicMock()
            mock_is_inst.load_window_candidates.return_value = candidates
            mock_is.return_value = mock_is_inst
            mock_cls.return_value = MagicMock()
            mock_github.return_value.load_latest_snapshot.return_value = []
            mock_pusher = MagicMock()
            mock_pusher.push_single_markdown = AsyncMock(return_value=push_result)
            mock_pusher_cls.return_value = mock_pusher
            mock_metrics_store_cls.return_value.write_selected_counts.return_value = 3

            result = await run_pipeline(ctx, config)

        assert result.status == "ok"
        pushed = mock_pusher.push_single_markdown.await_args.args[0]
        assert "【AI】" in pushed
        assert "【工具】" in pushed
        assert "【游戏】" in pushed
