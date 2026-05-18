"""FastAPI entrypoint for the AI News Assistant service.

Provides health-check, service info, and a manual trigger endpoint.
An APScheduler runs the news pipeline at 09:00 daily.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI

from app.agents.news_agent import NewsAgent
from app.config import load_config
from app.pipeline.context import RunContext
from app.pipeline.news_pipeline import run_pipeline
from app.scheduler.jobs import create_scheduler, run_ingest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

config = load_config()
agent = NewsAgent(config)
scheduler = create_scheduler(agent, config.tz)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    # 后台跑首次 ingest，不阻塞服务启动
    asyncio.create_task(run_ingest())
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(
    title="Claw_news AI Assistant",
    description="RSS news collection → LLM summarization → WeCom push",
    version="0.2.0",
    lifespan=lifespan,
)


@app.get("/")
async def root():
    return {
        "service": "Claw_news AI Assistant",
        "version": "0.2.0",
        "scheduler": "APScheduler — 09:00 daily",
        "endpoints": {
            "health": "/health",
            "run_news": "POST /run/news",
        },
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/run/news")
async def run_news():
    now = datetime.now()
    ctx = RunContext(
        trigger_mode="http",
        time_window_start=now.strftime("%Y-%m-%dT00:00:00"),
        time_window_end=now.strftime("%Y-%m-%dT%H:%M:%S"),
    )
    result = await run_pipeline(ctx, config)
    return {
        "status": result.status,
        "fetched_count": result.selected_count,
        "pushed": result.pushed,
        "summary_preview": result.summary_preview,
        "errors": result.errors,
    }
