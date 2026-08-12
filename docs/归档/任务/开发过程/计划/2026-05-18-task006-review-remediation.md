# Task006 Review Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the three blocking findings from the Task006 review without expanding scope.

**Architecture:** Keep the unified pipeline intact and tighten two existing boundaries: the ingestion store must perform true candidate-level window filtering, and the publish pipeline must enforce `ai_only` before classification and scoring. Documentation updates align the public operating model with the already-implemented service-first flow.

**Tech Stack:** Python, pytest, FastAPI/APScheduler docs, existing file-backed ingestion store

---

### Task 1: Enforce candidate-level time windows

**Files:**
- Modify: `tests/test_ingestion_store.py`
- Modify: `app/storage/ingestion_store.py`

- [ ] Add a failing regression test proving a candidate in the same day directory but with `fetched_at` later than `time_window_end` is excluded.
- [ ] Run the focused test and confirm it fails for the expected reason.
- [ ] Add minimal filtering in `load_window_candidates()` so each raw item must have an in-window timestamp before folding.
- [ ] Re-run the focused ingestion-store tests.

### Task 2: Enforce `ai_only` at publish time

**Files:**
- Modify: `tests/test_main.py`
- Modify: `app/pipeline/news_pipeline.py`

- [ ] Add a failing regression test proving mixed `ai` + `game` candidates only publish the AI record.
- [ ] Run the focused test and confirm it fails for the expected reason.
- [ ] Filter candidates by `ctx.publish_scope` before classifier/scoring work.
- [ ] Re-run the focused pipeline tests.

### Task 3: Align operating documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/operations/deploy/server-guide.md`

- [ ] Replace stale task003 wording with task006 wording: service-first entrypoint, markdown push, one 09:00 publish job plus high-frequency ingest.
- [ ] Remove the old CLI config step from the formal deployment path and document `.env.verify + docker-compose.verify.yml` for verification.
- [ ] Re-read the affected sections to ensure the old formal path is no longer presented as current truth.

### Task 4: Verify remediation

**Files:**
- Read: `spec/task006/review.md`

- [ ] Run the focused pytest set covering ingestion store, pipeline, scheduler/API, renderer, state store, classifier, and data contracts.
- [ ] Re-check each prior blocker against the code/docs.
- [ ] Update review status only if the blockers are actually closed.
