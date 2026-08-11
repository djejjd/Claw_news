"""交付决策层测试：仅飞书配置时走 feishu 分支，pending 文件成功后删除。"""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.delivery.store import PendingDeliveryStore
from app.pipeline import news_pipeline as np
from app.pipeline.context import RunContext


@pytest.fixture(autouse=True)
def _restore_data_dir():
    """每个测试把 np._DATA_DIR 改到 tmp_path 后，恢复原值，避免污染其他测试文件。"""
    original = np._DATA_DIR
    yield
    np._DATA_DIR = original


def make_ctx():
    return RunContext(
        trigger_mode="scheduler",
        period="morning",
        time_window_start="2026-08-12T00:00:00",
        time_window_end="2026-08-12T08:00:00",
    )


def make_config(**overrides):
    """wecom 空、telegram 空、feishu 有值的最小 config。"""
    base = {
        "wecom_webhook_url": "",
        "telegram_bot_token": None,
        "telegram_chat_id": None,
        "telegram_proxy": None,
        "feishu_app_id": "cli_test",
        "feishu_app_secret": "secret_test",
        "feishu_chat_id": "oc_test",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def make_stores(tmp_path: Path):
    np._DATA_DIR = tmp_path  # 重定向 data 目录到临时目录
    return {
        "state_store": __import__("infra.storage.state_store", fromlist=["StateStore"]).StateStore(
            tmp_path
        ),
        "metrics_store": __import__(
            "app.storage.source_metrics_store", fromlist=["SourceMetricsStore"]
        ).SourceMetricsStore(tmp_path),
        "exposure_store": __import__(
            "app.storage.github_exposure_store", fromlist=["GitHubExposureStore"]
        ).GitHubExposureStore(tmp_path),
    }


def test_build_pending_payload_feishu_only(tmp_path):
    """仅飞书时 _build_pending_payload 只写 feishu 通道，不写 wecom/telegram。"""
    np._DATA_DIR = tmp_path
    payload = np._build_pending_payload(
        ctx=make_ctx(),
        markdown="# 热点",
        telegram_messages=[],
        feishu_card={"config": {}, "elements": []},
        config=make_config(),
        selected_count=3,
        daily_judgement="今日动作频频。",
        source_failures=[],
        headline_payload=[],
        github_ranked=[],
        github_recommendations={},
        published_urls=[],
        published_keys=[],
        selection_evidence=[],
        relevance_rejected=[],
        selected_counts_by_source={},
        metric_rows=[],
    )
    assert "feishu" in payload["channels"]
    assert "wecom" not in payload["channels"]
    assert "telegram" not in payload["channels"]
    assert "feishu_card" in payload["messages"]


def test_build_pending_payload_wecom_and_feishu(tmp_path):
    """wecom + feishu 双配置时两个通道都写入。"""
    np._DATA_DIR = tmp_path
    payload = np._build_pending_payload(
        ctx=make_ctx(),
        markdown="# 热点",
        telegram_messages=[],
        feishu_card={"config": {}, "elements": []},
        config=make_config(
            wecom_webhook_url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=x"
        ),
        selected_count=3,
        daily_judgement="",
        source_failures=[],
        headline_payload=[],
        github_ranked=[],
        github_recommendations={},
        published_urls=[],
        published_keys=[],
        selection_evidence=[],
        relevance_rejected=[],
        selected_counts_by_source={},
        metric_rows=[],
    )
    assert "wecom" in payload["channels"]
    assert "feishu" in payload["channels"]
    assert "telegram" not in payload["channels"]


def test_deliver_with_pending_feishu_only_success(tmp_path, monkeypatch):
    """仅飞书时 _deliver_with_pending 走 feishu 分支，status=ok、pending 文件删除。"""

    async def fake_attempt_feishu(card, app_id, app_secret, chat_id):
        return True, None

    async def fake_attempt_wecom(markdown, url):
        raise AssertionError("wecom 不应被调用（wecom 停用）")

    monkeypatch.setattr(np, "_attempt_feishu", fake_attempt_feishu)
    monkeypatch.setattr(np, "_attempt_wecom", fake_attempt_wecom)
    # _finalize_delivery 需要 state_store/metrics 真实可写，用 tmp_path
    stores = make_stores(tmp_path)

    result = asyncio.run(
        np._deliver_with_pending(
            ctx=make_ctx(),
            config=make_config(),
            markdown="# 热点",
            telegram_messages=[],
            feishu_card={"config": {}, "elements": []},
            selected_count=3,
            daily_judgement="今日动作频频。",
            source_failures=[],
            headline_payload=[],
            github_ranked=[],
            github_recommendations={},
            published_urls=["https://x.com/1"],
            published_keys=["www.x.com/1"],
            selection_evidence=[],
            relevance_rejected=[],
            # 空 selected_counts_by_source：tmp 全新 stores 无历史 metric 行，
            # 非空 dict 会让 write_selected_counts 返回 0 < len，误报 source_metrics_write_failed。
            selected_counts_by_source={},
            metric_rows=[],
            state_store=stores["state_store"],
            metrics_store=stores["metrics_store"],
            exposure_store=stores["exposure_store"],
        )
    )
    assert result.status == "ok"
    assert result.pushed is True
    # pending 文件应已删除（全成功分支）
    pending_dir = tmp_path / "pending_deliveries"
    assert not list(pending_dir.glob("2026-08-12-morning.json")) if pending_dir.exists() else True


def test_resume_pending_delivery_feishu_only_success(tmp_path, monkeypatch):
    """仅飞书时 _resume_pending_delivery 走 feishu 分支，status=ok、pending 文件删除。"""

    async def fake_attempt_feishu(card, app_id, app_secret, chat_id):
        return True, None

    async def fake_attempt_wecom(markdown, url):
        raise AssertionError("wecom 不应被调用（wecom 停用）")

    async def fake_attempt_telegram(messages, bot_token, chat_id, proxy=None):
        raise AssertionError("telegram 不应被调用（telegram 停用）")

    monkeypatch.setattr(np, "_attempt_feishu", fake_attempt_feishu)
    monkeypatch.setattr(np, "_attempt_wecom", fake_attempt_wecom)
    monkeypatch.setattr(np, "_attempt_telegram", fake_attempt_telegram)

    # _finalize_delivery 需要 state_store/metrics 真实可写，用 tmp_path
    stores = make_stores(tmp_path)
    pending_store = PendingDeliveryStore(tmp_path)

    # 手工构造 feishu-only 的 pending payload（结构与 _build_pending_payload 输出一致）
    payload = {
        "delivery_id": "2026-08-12-morning-test",
        "channels": {
            "feishu": {"enabled": True, "status": "pending"},
        },
        "messages": {
            "feishu_card": {"config": {}, "elements": []},
        },
        "finalization": {
            "date": "2026-08-12",
            "period": "morning",
            "trigger_mode": "scheduler",
            "headline_items": [],
            "daily_judgement": "今日动作频频。",
            "source_failures": [],
            "published_urls": ["https://x.com/1"],
            "published_keys": ["www.x.com/1"],
            "github_projects": [],
            "github_recommendations": {},
            "selection_evidence": [],
            "relevance_rejections": [],
            # 空 selected_counts_by_source：tmp 全新 stores 无历史 metric 行，
            # 非空 dict 会让 write_selected_counts 返回 0 < len，误报 source_metrics_write_failed。
            "selected_counts_by_source": {},
            "metric_rows": [],
        },
    }
    pending_store.save("2026-08-12", "morning", payload)

    result = asyncio.run(
        np._resume_pending_delivery(
            ctx=make_ctx(),
            config=make_config(),
            pending_payload=payload,
            state_store=stores["state_store"],
            metrics_store=stores["metrics_store"],
            exposure_store=stores["exposure_store"],
            pending_store=pending_store,
        )
    )
    assert result.status == "ok"
    assert result.pushed is True
    # pending 文件应已删除（全成功分支）
    assert not (tmp_path / "pending_deliveries" / "2026-08-12-morning.json").exists()
