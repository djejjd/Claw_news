# AI Source Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the AI digest with configurable multi-source RSS, a fixed three-item GitHub supplement, and visible ingest health.

**Architecture:** Keep the existing unified news pipeline as the primary digest path. Add a narrow AI RSS config layer, a separate GitHub snapshot flow that never enters headline ranking, and a lightweight ingest-status file surfaced through `/health`.

**Tech Stack:** Python, pytest, FastAPI, APScheduler, httpx, existing file-backed stores

---

## File Structure

- `collectors/ai_rss.py` — dedicated AI RSS feed configuration parser and defaults
- `collectors/github.py` — GitHub repository DTO and Search API collector
- `app/storage/github_store.py` — file-backed GitHub snapshot persistence
- `app/storage/ingest_status_store.py` — file-backed latest-ingest status persistence
- `app/renderers/wecom_markdown.py` — append optional GitHub supplement section
- `app/scheduler/jobs.py` — run AI RSS + HuggingFace + GitHub ingest and persist status
- `app/pipeline/news_pipeline.py` — load GitHub supplement for publish rendering only
- `app/main.py` — expose ingest status through `/health`
- `.env.example`, `README.md` — document AI RSS and GitHub configuration
- tests for each new boundary

### Task 1: Add configurable AI RSS sources

**Files:**
- Create: `collectors/ai_rss.py`
- Modify: `app/scheduler/jobs.py`
- Modify: `.env.example`
- Test: `tests/test_ai_rss.py`

- [ ] Add failing tests for default feeds, append mode, replace mode, and malformed config rejection.
- [ ] Run `./venv/bin/pytest -q tests/test_ai_rss.py` and confirm failure because the module is missing.
- [ ] Implement `AiRssFeed`, built-in defaults, and `load_ai_rss_feeds()` parsing `AI_RSS_FEEDS` plus `AI_RSS_MODE`.
- [ ] Update ingest construction to pass the AI-only feed list into `RssCollector`.
- [ ] Document `AI_RSS_FEEDS` and `AI_RSS_MODE` in `.env.example`.
- [ ] Re-run focused tests and commit.

### Task 2: Add GitHub supplemental ingestion

**Files:**
- Create: `collectors/github.py`
- Create: `app/storage/github_store.py`
- Modify: `app/scheduler/jobs.py`
- Test: `tests/test_github_collector.py`
- Test: `tests/test_github_store.py`

- [ ] Add failing collector tests for parsing Search API payloads, capping to 3 items, and empty results.
- [ ] Add failing store tests for writing and loading `data/github/YYYY-MM-DD/repos.json`.
- [ ] Run focused tests and confirm failures.
- [ ] Implement `GitHubRepoItem` and `GitHubCollector` using Search API with topic-scoped queries and a three-item cap.
- [ ] Implement `GitHubStore` with `write_snapshot()` and `load_latest_snapshot()`.
- [ ] Extend ingest job to fetch GitHub best-effort and persist a snapshot without blocking candidate ingestion.
- [ ] Re-run focused tests and commit.

### Task 3: Render GitHub supplement without changing headline ranking

**Files:**
- Modify: `app/renderers/wecom_markdown.py`
- Modify: `app/pipeline/news_pipeline.py`
- Test: `tests/test_wecom_markdown_renderer.py`
- Test: `tests/test_main.py`

- [ ] Add failing renderer test showing a three-item GitHub section after the main digest.
- [ ] Add failing pipeline test proving GitHub items are rendered but never sent into the LLM headline input.
- [ ] Run focused tests and confirm failures.
- [ ] Extend renderer to accept optional GitHub items and append a concise supplement section.
- [ ] Load the latest GitHub snapshot in publish flow and pass it only to the renderer.
- [ ] Re-run focused tests and commit.

### Task 4: Add ingest observability

**Files:**
- Create: `app/storage/ingest_status_store.py`
- Modify: `app/scheduler/jobs.py`
- Modify: `app/main.py`
- Test: `tests/test_ingest_status_store.py`
- Test: `tests/test_app_api.py`

- [ ] Add failing tests for ingest status persistence and `/health` response shape.
- [ ] Run focused tests and confirm failures.
- [ ] Implement `IngestStatusStore` with write/load helpers for `data/ingestion_status.json`.
- [ ] Extend ingest flow to record `last_ingest_at`, `last_item_count`, `successful_sources`, and `failed_sources`.
- [ ] Update `/health` to include the latest ingest status.
- [ ] Re-run focused tests and commit.

### Task 5: Update docs and verify the whole slice

**Files:**
- Modify: `README.md`
- Modify: `docs/operations/deploy/server-guide.md`

- [ ] Document default + configurable AI RSS behavior, GitHub supplement, and health observability.
- [ ] Run the full focused suite covering new modules plus the existing task006 pipeline slice.
- [ ] Re-read the Chinese spec and verify every requirement has a corresponding implementation.
- [ ] Commit the docs and any final cleanups.
