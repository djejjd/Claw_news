"""为前端浏览器测试提供隔离的真实公共内容 API 服务。"""

from __future__ import annotations

import argparse
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import uvicorn
from fastapi import FastAPI

# 直接执行本文件时，Python 只会把 tests/ 加入模块搜索路径。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pipeline.candidate import CandidateItem
from app.publication import routes
from app.publication.store import PublicationStore

TEST_NOW = datetime(2026, 8, 17, 12, 0, 0)
_SCENARIOS = {"success", "empty-digest", "empty-articles", "unavailable"}


def _seed(store: PublicationStore, *, scenario: str) -> None:
    if scenario == "empty-articles":
        return

    store.publish_sources(
        [
            {
                "name": "test-source",
                "display_name": "测试来源",
                "default_category": "ai",
                "site_url": "https://example.test",
            }
        ]
    )
    store.publish_articles(
        [
            CandidateItem(
                title="测试公共文章",
                url="https://example.test/article",
                summary="用于浏览器测试的公开摘要",
                source="test-source",
                category="ai",
                topic="测试主题",
                published_at="2026-08-17T10:00:00+00:00",
                fetched_at="2026-08-17T10:01:00+00:00",
                canonical_key="example.test/article",
            )
        ]
    )
    if scenario == "empty-digest":
        return

    store.publish_digest(
        digest_date="2026-08-17",
        version=1,
        published_at=datetime(2026, 8, 17, 11, 0, 0),
        daily_judgement="测试日报判断",
        items=[
            {
                "canonical_key": "example.test/article",
                "position": 1,
                "core_summary": "测试核心摘要",
                "importance": "high",
                "trend": "up",
                "topic_label": "测试主题",
            }
        ],
        github_projects=[{"full_name": "example/test-project", "recommendation": "测试推荐"}],
    )


def create_app(database_path: Path, *, scenario: str = "success") -> FastAPI:
    """创建只挂载公共路由的测试应用，不触发生产启动副作用。"""
    if scenario not in _SCENARIOS:
        raise ValueError(f"unknown scenario: {scenario}")

    store = PublicationStore(f"sqlite:///{database_path}")
    store.create_schema()
    if scenario != "unavailable":
        _seed(store, scenario=scenario)

    app = FastAPI()
    app.state.config = SimpleNamespace(
        publication_enabled=scenario != "unavailable",
        publication_database_url=str(store.engine.url) if scenario != "unavailable" else None,
        tz="UTC",
    )
    app.include_router(routes.router)
    return app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--scenario", choices=sorted(_SCENARIOS), default="success")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="claw-news-frontend-e2e-") as directory:
        # 子进程专用的固定时钟保证十天窗口和默认日报日期可复现。
        routes.local_now = lambda _tz: TEST_NOW
        app = create_app(Path(directory) / "publication.db", scenario=args.scenario)
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
