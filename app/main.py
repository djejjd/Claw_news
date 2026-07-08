"""FastAPI entrypoint for the AI News Assistant service.

Provides health-check, service info, and a manual trigger endpoint.
An APScheduler runs the news pipeline at 09:00 daily.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.agents.news_agent import NewsAgent
from app.config import load_config
from app.scheduler.jobs import create_scheduler
from app.storage.ingest_status_store import IngestStatusStore

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
    return {"status": "healthy", "ingest": IngestStatusStore().load_status()}


@app.post("/run/news")
async def run_news():
    return await agent.run_once(trigger_mode="http")
