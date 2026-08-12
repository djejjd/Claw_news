# Task006 Unified Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify the old CLI pipeline and new service pipeline into a single FastAPI + APScheduler service with file-based ingestion store, topic classifier, upgraded scoring, and single WeCom markdown output.

**Architecture:** High-frequency ingest (every 30min from 00:00) writes CandidateItems to `data/ingestion/YYYY-MM-DD/candidates.jsonl`. Publish at 09:00 reads from ingestion store, classifies topics, scores, merges, LLM summarizes to structured JSON, renders to WeCom markdown, pushes single message, persists digest-shaped JSON.

**Tech Stack:** FastAPI, APScheduler, existing collectors (rss/huggingface/taptap), existing Merger (modified), existing WeComPusher (adapted), existing StateStore (adapted), httpx, Python 3.11+ dataclasses

**Key Decisions:**
- Ingest: 00:00–09:00 every 30min (18 rounds before first publish)
- Publish: 09:00 only (morning, ai_only)
- canonical_key = domain+path (no query/fragment)
- LLM: prompt-constrained JSON output + parse fallback (no API JSON mode)
- CandidateItem: new dataclass, HotItem→CandidateItem conversion
- `app/tools/crawler.py`: deleted, ingest job uses collectors
- `app/tools/wecom.py` send_text: kept for error notifications only
- Old CLI main.py: compat shell delegating to unified pipeline

---
