# Open Source Cleanup Design

**Date**: 2026-05-16
**Status**: approved
**Goal**: 核心代码公开，部署配置与开发过程文档保留在私有仓库

## Scope

在现有仓库就地清理（方案 A），确保 git tracked 文件全部为可公开内容，敏感文件通过 `.gitignore` 排除。

## File Classification

### Keep Tracked (public)

All Python source, build config, CI, templates:

- `main.py`
- `collectors/` (base.py, rss_sources.py, huggingface.py, taptap.py, utils.py, `__init__.py`)
- `aggregator/merger.py` + `__init__.py`
- `pusher/wecom.py` + `__init__.py`
- `infra/config/settings.py` + `__init__.py`
- `infra/storage/state_store.py` + `__init__.py`
- `tests/` (all 11 files)
- `pyproject.toml`, `requirements.txt`, `Makefile`
- `config.example.yaml`, `deploy.example.sh`, `.env.example`
- `.github/workflows/ci.yml`
- `.gitignore`
- `README.md`
- `CLAUDE.md`

### Stop Tracking (git rm --cached, keep locally)

| File/Dir | Reason |
|----------|--------|
| `docs/operations/launchd/com.lanser.clawnews.morning.plist` | Hardcoded `/Users/lanser/` path |
| `docs/operations/launchd/com.lanser.clawnews.evening.plist` | Hardcoded `/Users/lanser/` path |
| `docs/operations/launchd/com.lanser.clawnews.plist` | Hardcoded `/Users/lanser/` path |
| `docs/superpowers/` | Internal dev process docs (design/spec/plan/review) |
| `spec/` | Internal task specs (task001/task002) |

### Add to .gitignore

```
.claude/
.prompt/
```

These are local Claude Code config and prompt templates — not project code.

### Already Excluded (no action needed)

- `config.yaml` (contains real webhook key — verify never committed)
- `data/` (runtime logs, pushed_urls.json, daily digests, .task.lock)
- `deploy.sh` (crontab manipulation with hardcoded paths)
- `venv/`, `.env`, `.ruff_cache/`

### New Files to Create

- `LICENSE` — MIT
- `docs/operations/launchd/com.lanser.clawnews.morning.plist.example`
- `docs/operations/launchd/com.lanser.clawnews.evening.plist.example`
- Plist templates use `{{PROJECT_DIR}}` placeholder instead of `/Users/lanser/Code/Claw_news`
- Update `README.md` — add License section

## Pre-flight Check

Before cleanup, verify `config.yaml` was never committed:

```bash
git log --all --full-history -- config.yaml
```

If history contains the webhook key, run `git filter-branch` or `bfg` to purge before making the repo public.

## Commit Plan

Single commit with the following operations:

1. `git rm --cached` the 5 items listed in "Stop Tracking"
2. Append `.claude/` and `.prompt/` to `.gitignore`
3. Add `LICENSE` (MIT)
4. Add 3 plist example files with placeholder paths
5. Update `README.md` with license info
