# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

All commands use the venv created by `make install`:

```bash
make install       # Create venv + install editable package with dev deps
make test          # Run all tests: pytest -v
make lint          # Ruff linter check
make format        # Ruff formatter
make dry-run       # Morning run without pushing (prints formatted output)
make run-morning   # Full morning pipeline: collect → score → push
make run-evening   # Full evening pipeline
```

Run a single test: `./venv/bin/pytest tests/test_merger.py::test_function_name -v`

CI (`.github/workflows/ci.yml`) runs `pip install -e ".[dev]"` then `ruff format --check`, `ruff check`, and `pytest -v`. Python 3.12 in CI, 3.11+ locally.

## Architecture

**Pipeline**: Collectors → Aggregator → Pusher, orchestrated by `main.py`.

### Data model

`collectors/base.py` defines `HotItem` — the single data object flowing through the pipeline. Fields: `title`, `url`, `summary`, `source`, `category` (Literal["ai","game","device"]), `source_score`, `timestamp`, `keyword_hit`, `pub_date`. It also defines `time_modifier()` (period-aware decay) and `time_decay_bonus()` (age-based recency boost).

### Collectors (`collectors/`)

Each collector produces `List[HotItem]`. All are async. `safe_collect()` wraps every collector — failures are logged, never crash the pipeline.

- **RssCollector** (`rss_sources.py`): Multi-feed RSS parser. `FEED_CONFIGS` defines 4 sources (qbitai→ai, sspai/ithome→device, yystv→game). Default `source_score=5.0` — the Merger computes the real 3D score later. Sets `keyword_hit` via `check_keyword_hit()`.
- **HfDailyPapersCollector** (`huggingface.py`): HuggingFace daily papers API. Uses `curl_cffi` with Chrome 131 impersonation for TLS fingerprinting. Scores papers by normalizing upvotes to 0–10. Concurrently translates all abstracts to Chinese via `deep-translator` (Google Translate, semaphore-limited to 3).
- **TapTapCollector** (`taptap.py`): Scrapes TapTap download rankings via `curl_cffi` + BeautifulSoup. Scores by rank normalization.

Each collector accepts an optional `client` parameter for test injection (httpx.AsyncClient or equivalent), falling back to its real HTTP client when not provided.

### Aggregator (`aggregator/`)

`Merger.merge()` implements the competition algorithm:

1. Group items by category, dedup by URL (keep higher score)
2. Compute 3D scores for RSS items: `position_score(rank) + keyword_bonus(+1.0) + time_modifier(pub_date, period)`. HF/TapTap items keep their original `source_score`.
3. **Step 1 — Keyword guarantee**: each source gets at least 1 slot (preferring keyword-hit items)
4. **Step 2 — Open competition**: remaining slots filled by highest-scoring items across all sources
5. Final sort by score, top 5 per category returned

### Pusher (`pusher/`)

`WeComPusher` posts markdown to WeCom webhook. `format_message()` builds the markdown with category emojis, `[新]/[续]` markers (tracked via `pushed_urls` set), `[EN]` for HuggingFace papers, and source + region labels. `PushResult` is a structured dataclass.

### Infrastructure (`infra/`)

- **Settings** (`config/settings.py`): Loads YAML config, overlays `PUSHER_WECOM_WEBHOOK` env var, validates webhook URL format for non-dry runs. Uses frozen dataclasses.
- **StateStore** (`storage/state_store.py`): Persists `pushed_urls.json` (dedup across runs) and daily digest JSONs (`data/YYYY-MM-DD/{morning,evening}.json`). All writes are atomic (write to `.tmp`, then rename).

### Main orchestration (`main.py`)

Flow: load config → file lock (prevents concurrent runs via `portalocker`) → collect → merge → push (or dry-run print). `run_push_sequence()` pushes per category, merges pushed URLs into state after each success, writes daily digest, and exits with code 1 on any failure.

## Key conventions

- Config lives in `config.yaml` (gitignored), templated from `config.example.yaml`
- `data/` is gitignored — runtime state only
- Tests use `pytest-asyncio` with `asyncio_mode = "auto"`; injectable HTTP clients enable testing without network
- `curl-cffi` is used wherever TLS fingerprinting matters (HF API, TapTap); `httpx` for WeCom webhook calls
- RSS feeds can be overridden via `rss_feeds` in config.yaml; defaults are in `FEED_CONFIGS`
