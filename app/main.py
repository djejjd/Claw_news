"""FastAPI entrypoint for the AI News Assistant service.

Provides health-check, service info, and a manual trigger endpoint.
An APScheduler runs the news pipeline at 09:00 daily.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from importlib.metadata import version as package_version

from fastapi import FastAPI

from app.agents.news_agent import NewsAgent
from app.config import load_config
from app.content.clock import local_now
from app.scheduler.jobs import create_scheduler
from app.storage.ingest_status_store import IngestStatusStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

config = load_config()
agent = NewsAgent(config)
scheduler = create_scheduler(agent, config.tz, config.source_failure_degraded_threshold)
APP_VERSION = package_version("claw-news")


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(
    title="Claw_news AI Assistant",
    description="RSS news collection → LLM summarization → WeCom push",
    version=APP_VERSION,
    lifespan=lifespan,
)


@app.get("/")
async def root():
    return {
        "service": "Claw_news AI Assistant",
        "version": APP_VERSION,
        "scheduler": "APScheduler — 09:00 daily",
        "endpoints": {
            "health": "/health",
            "run_news": "POST /run/news",
        },
    }


@app.get("/health")
async def health():
    ingest_status = IngestStatusStore().load_status()

    # 判断 ingest 是否陈旧（超过 1 小时未更新）
    ingest_fresh = True
    last_ingest_at = ingest_status.get("last_ingest_at")
    if last_ingest_at:
        try:
            from datetime import datetime

            last_dt = datetime.fromisoformat(last_ingest_at)
            if last_dt.tzinfo is not None:
                from zoneinfo import ZoneInfo

                last_dt = last_dt.astimezone(ZoneInfo(config.tz)).replace(tzinfo=None)
            ingest_fresh = (local_now(config.tz) - last_dt).total_seconds() < 3600
        except ValueError:
            ingest_fresh = False

    # 加载最近 publish 结果
    from pathlib import Path

    publish_status_path = Path(__file__).resolve().parent.parent / "data" / "publish_status.json"
    publish_status = {}
    if publish_status_path.exists():
        try:
            import json

            publish_status = json.loads(publish_status_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass

    # 汇总 source 状态
    source_status = {}
    for src in ingest_status.get("successful_sources", []):
        source_status[src] = "ok"
    for entry in ingest_status.get("failed_sources", []):
        name = entry.split(":")[0] if ":" in entry else entry
        source_status[name] = "failed"
    for entry in ingest_status.get("degraded_sources", []):
        name = entry.get("source") if isinstance(entry, dict) else None
        if name and source_status.get(name) != "failed":
            source_status[name] = "degraded"

    has_failed_source = any(s == "failed" for s in source_status.values())
    has_degraded_source = any(s == "degraded" for s in source_status.values())
    last_publish_failed = publish_status.get("status") in {"failed", "error"}
    last_publish_degraded = publish_status.get("status") == "degraded"

    # 综合判定：healthy < degraded < unhealthy
    if has_failed_source and last_publish_failed:
        overall = "unhealthy"
    elif has_failed_source or not ingest_fresh or has_degraded_source or last_publish_degraded:
        overall = "degraded"
    elif not publish_status:
        overall = "healthy"  # 刚启动，还没推送过
    else:
        overall = "healthy"

    return {
        "status": overall,
        "ingest": ingest_status,
        "ingest_fresh": ingest_fresh,
        "last_publish": publish_status,
        "sources": source_status,
        "scheduler": "APScheduler — 09:00 daily",
    }


@app.post("/run/news")
async def run_news():
    return await agent.run_once(trigger_mode="http")
