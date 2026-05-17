# Claw_news M1+M2 Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Design doc:** `docs/tasks/task001/design.md`

**Goal:** Implement M1 security/correctness fixes and M2 engineering foundations without changing core scoring or message behavior.

**Architecture:** Keep the current script-style runtime and business flow, but introduce three narrow boundaries: `Settings` for configuration, `StateStore` for persistent file state, and `push_category()` for category-level delivery transactions. Preserve current CLI/data semantics while making installation, testing, and partial-success behavior deterministic.

**Tech Stack:** Python 3.11+, dataclasses, pathlib, PyYAML, httpx, portalocker, pytest, pytest-asyncio, pytest-httpx, ruff, GitHub Actions

---

## File Structure

### New files (18)

| File | Purpose |
|---|---|
| `infra/__init__.py` | Package marker |
| `infra/config/__init__.py` | Package marker |
| `infra/config/settings.py` | Centralized config loading + env override + validation |
| `infra/storage/__init__.py` | Package marker |
| `infra/storage/state_store.py` | Atomic pushed_urls writes + category-level daily digest |
| `collectors/utils.py` | Shared `safe_collect()` helper |
| `tests/test_settings.py` | Settings loading, env override, validation |
| `tests/test_state_store.py` | Atomic merge, partial digest writes, missing-file tolerance |
| `tests/test_main.py` | Category-by-category transaction orchestration + task lock |
| `pyproject.toml` | Canonical metadata, deps, pytest, ruff config |
| `Makefile` | Unified local workflow |
| `.github/workflows/ci.yml` | Clean-env install → lint → format-check → test |
| `.env.example` | Env var template (NOT auto-loaded) |
| `deploy.example.sh` | Standardized deploy template (NOT gitignored) |

### Modified files (11)

| File | Changes |
|---|---|
| `main.py` | Settings/StateStore, `run_push_sequence()`, task lock, `run_id` in log format |
| `pusher/wecom.py` | `PushResult`, `WeComError`, `push_category()` with errcode validation |
| `collectors/rss_sources.py` | `__init__` injects `feed_configs` + `keywords` + `fetch_count`, remove `_load_config()` |
| `collectors/huggingface.py` | `__init__` injects `fetch_count`, remove `_load_config()` |
| `collectors/taptap.py` | `__init__` injects `fetch_count`, remove `_load_config()` |
| `tests/test_resilience.py` | Remove shadow `safe_collect()`, import from `collectors.utils` |
| `tests/test_wecom.py` | `push()` → `push_category()`, add errcode tests |
| `README.md` | Quick start via `make`, `.env` notes, remove `ithome.py` refs |
| `.gitignore` | Add `.env`, `.ruff_cache/`, `data/.task.lock` |
| `requirements.txt` | Add `portalocker`, keep as compatibility reference |
| `config.example.yaml` | Unchanged (already has placeholder) |

### Files intentionally unchanged

- `aggregator/merger.py` — scoring logic unchanged
- `collectors/base.py` — `HotItem` model unchanged
- `pusher/wecom.py` `format_message()` — pure function, interface unchanged
- `data/` directory layout (`YYYY-MM-DD/<period>.json` and `pushed_urls.json`)

---

## Task 1: Add Settings Boundary

**Files:**
- Create: `infra/__init__.py`
- Create: `infra/config/__init__.py`
- Create: `infra/config/settings.py`
- Create: `tests/test_settings.py`
- Modify: `main.py`
- Modify: `collectors/rss_sources.py`
- Modify: `collectors/huggingface.py`
- Modify: `collectors/taptap.py`

- [ ] **Step 1: Write the failing settings tests**

```python
# tests/test_settings.py
from pathlib import Path

import pytest

from infra.config.settings import Settings


def test_settings_loads_yaml_defaults(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
collectors:
  fetch_count: 10
  top_n: 5
  sources:
    rss: true
    huggingface: true
    taptap: false
rss_feeds:
  - url: "https://example.com/feed"
    category: "ai"
    source: "demo"
keywords:
  ai: ["AI"]
pusher:
  wecom_webhook: ""
""".strip(),
        encoding="utf-8",
    )

    settings = Settings.load(config_path)

    assert settings.fetch_count == 10
    assert settings.top_n == 5
    assert settings.collector_sources.taptap is False
    assert settings.rss_feeds[0]["source"] == "demo"


def test_settings_env_overrides_yaml(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
collectors:
  fetch_count: 10
  top_n: 5
  sources:
    rss: true
    huggingface: true
    taptap: true
rss_feeds: []
keywords: {}
pusher:
  wecom_webhook: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=from-yaml"
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv(
        "PUSHER_WECOM_WEBHOOK",
        "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=from-env",
    )

    settings = Settings.load(config_path)

    assert settings.wecom_webhook.endswith("from-env")


def test_validate_for_run_allows_empty_webhook_in_dry_run(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
collectors:
  fetch_count: 10
  top_n: 5
  sources:
    rss: true
    huggingface: true
    taptap: true
rss_feeds: []
keywords: {}
pusher:
  wecom_webhook: ""
""".strip(),
        encoding="utf-8",
    )

    settings = Settings.load(config_path)

    settings.validate_for_run(dry_run=True)


def test_validate_for_run_rejects_invalid_live_webhook(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
collectors:
  fetch_count: 10
  top_n: 5
  sources:
    rss: true
    huggingface: true
    taptap: true
rss_feeds: []
keywords: {}
pusher:
  wecom_webhook: "https://example.com/not-wecom"
""".strip(),
        encoding="utf-8",
    )

    settings = Settings.load(config_path)

    with pytest.raises(ValueError, match="wecom webhook"):
        settings.validate_for_run(dry_run=False)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_settings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'infra'`

- [ ] **Step 3: Implement the settings package skeleton**

```python
# infra/config/settings.py
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class CollectorSourceFlags:
    rss: bool = True
    huggingface: bool = True
    taptap: bool = True


@dataclass(frozen=True)
class Settings:
    fetch_count: int
    top_n: int
    collector_sources: CollectorSourceFlags
    rss_feeds: list[dict]
    keywords: dict[str, list[str]]
    wecom_webhook: str

    @classmethod
    def load(cls, config_path: Path) -> "Settings":
        if not config_path.exists():
            raise ValueError(f"config file not found: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        collectors = raw.get("collectors", {})
        source_flags = collectors.get("sources", {})
        webhook = os.getenv("PUSHER_WECOM_WEBHOOK") or raw.get("pusher", {}).get("wecom_webhook", "")

        return cls(
            fetch_count=collectors.get("fetch_count", 10),
            top_n=collectors.get("top_n", 5),
            collector_sources=CollectorSourceFlags(
                rss=source_flags.get("rss", True),
                huggingface=source_flags.get("huggingface", True),
                taptap=source_flags.get("taptap", True),
            ),
            rss_feeds=raw.get("rss_feeds", []),
            keywords=raw.get("keywords", {}),
            wecom_webhook=webhook,
        )

    def validate_for_run(self, dry_run: bool) -> None:
        if dry_run:
            return
        prefix = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key="
        if not self.wecom_webhook.startswith(prefix) or not self.wecom_webhook[len(prefix):]:
            raise ValueError("invalid wecom webhook")
```

- [ ] **Step 4: Refactor runtime callers to accept settings-derived values**

```python
# main.py
from infra.config.settings import Settings

CONFIG_PATH = Path(__file__).parent / "config.yaml"

settings = Settings.load(CONFIG_PATH)
settings.validate_for_run(dry_run=dry_run)
```

```python
# collectors/rss_sources.py
class RssCollector:
    def __init__(self, feed_configs: list[dict], keywords: dict, fetch_count: int):
        self.feeds = feed_configs
        self._keywords = keywords
        self._fetch_count = fetch_count
```

```python
# collectors/huggingface.py
class HfDailyPapersCollector:
    def __init__(self, fetch_count: int = 10, client=None):
        self._fetch_count = fetch_count
        self._client = client
```

```python
# collectors/taptap.py
class TapTapCollector:
    def __init__(self, fetch_count: int = 10, client=None):
        self._fetch_count = fetch_count
        self._client = client
```

- [ ] **Step 5: Run tests to verify settings work**

Run: `pytest tests/test_settings.py tests/test_rss_collector.py tests/test_huggingface.py tests/test_taptap.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add infra/__init__.py infra/config/__init__.py infra/config/settings.py tests/test_settings.py main.py collectors/rss_sources.py collectors/huggingface.py collectors/taptap.py
git commit -m "feat: add settings boundary for runtime config"
```

---

## Task 2: Add StateStore Boundary

**Files:**
- Create: `infra/storage/__init__.py`
- Create: `infra/storage/state_store.py`
- Create: `tests/test_state_store.py`
- Modify: `main.py`

- [ ] **Step 1: Write the failing state store tests**

```python
# tests/test_state_store.py
import json
from pathlib import Path

from infra.storage.state_store import StateStore


def test_load_pushed_urls_returns_empty_when_missing(tmp_path: Path):
    store = StateStore(tmp_path)
    assert store.load_pushed_urls() == set()


def test_merge_pushed_urls_deduplicates(tmp_path: Path):
    store = StateStore(tmp_path)
    merged = store.merge_pushed_urls({"https://a.com/1", "https://a.com/2"})
    merged = store.merge_pushed_urls({"https://a.com/2", "https://a.com/3"})
    assert merged == {
        "https://a.com/1",
        "https://a.com/2",
        "https://a.com/3",
    }


def test_write_daily_digest_category_builds_partial_record(tmp_path: Path):
    store = StateStore(tmp_path)
    store.write_daily_digest_category(
        period="morning",
        category="ai",
        items=[{"title": "AI 1", "url": "https://a.com/1"}],
    )
    store.write_daily_digest_category(
        period="morning",
        category="game",
        items=[{"title": "Game 1", "url": "https://g.com/1"}],
    )

    digest_files = list((tmp_path / store.today_str()).glob("morning.json"))
    assert len(digest_files) == 1
    payload = json.loads(digest_files[0].read_text(encoding="utf-8"))
    assert payload["ai"][0]["title"] == "AI 1"
    assert payload["game"][0]["title"] == "Game 1"
    assert "device" not in payload
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_state_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'infra.storage'`

- [ ] **Step 3: Implement the minimal StateStore**

```python
# infra/storage/state_store.py
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path


class StateStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.pushed_urls_path = data_dir / "pushed_urls.json"

    def today_str(self) -> str:
        return date.today().isoformat()

    def load_pushed_urls(self) -> set[str]:
        if not self.pushed_urls_path.exists():
            return set()
        try:
            with open(self.pushed_urls_path, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except (OSError, json.JSONDecodeError):
            return set()

    def merge_pushed_urls(self, urls: set[str]) -> set[str]:
        current = self.load_pushed_urls()
        merged = current | urls
        self._atomic_write_json(self.pushed_urls_path, sorted(merged))
        return merged

    def write_daily_digest_category(self, period: str, category: str, items: list[dict]) -> None:
        day_dir = self.data_dir / self.today_str()
        day_dir.mkdir(parents=True, exist_ok=True)
        digest_path = day_dir / f"{period}.json"

        if digest_path.exists():
            with open(digest_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        else:
            payload = {
                "period": period,
                "date": self.today_str(),
                "pushed_at": datetime.now().isoformat(),
            }

        payload[category] = items
        self._atomic_write_json(digest_path, payload)

    def _atomic_write_json(self, path: Path, payload) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        tmp_path.replace(path)
```

- [ ] **Step 4: Replace direct state file helpers in `main.py`**

```python
# main.py
from infra.storage.state_store import StateStore

DATA_DIR = Path(__file__).parent / "data"
state_store = StateStore(DATA_DIR)
pushed_urls = state_store.load_pushed_urls()
```

Delete or stop using:

```python
def load_pushed_urls() -> set: ...
def save_pushed_urls(urls: set): ...
def save_daily_digest(grouped: dict, period: str): ...
```

- [ ] **Step 5: Run tests to verify the boundary passes**

Run: `pytest tests/test_state_store.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add infra/storage/__init__.py infra/storage/state_store.py tests/test_state_store.py main.py
git commit -m "feat: add state store for pushed urls and daily digests"
```

---

## Task 3: Extract Shared `safe_collect()`

**Files:**
- Create: `collectors/utils.py`
- Modify: `main.py`
- Modify: `tests/test_resilience.py`

- [ ] **Step 1: Update the failing resilience tests to import the real helper**

```python
# tests/test_resilience.py
from collectors.utils import safe_collect
```

Delete the local test-only copy:

```python
async def safe_collect(name, collector):
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_resilience.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'collectors.utils'`

- [ ] **Step 3: Implement the shared helper**

```python
# collectors/utils.py
from __future__ import annotations

import logging
import traceback


async def safe_collect(name: str, collector):
    logger = logging.getLogger(__name__)
    try:
        items = await collector.collect()
        logger.info("%s: %d items", name, len(items))
        return items
    except Exception:
        logger.error("%s 采集失败:", name)
        logger.error(traceback.format_exc())
        return []
```

- [ ] **Step 4: Switch `main.py` to use the shared helper**

```python
# main.py
from collectors.utils import safe_collect

async def collect_all(settings: Settings):
    tasks = {}
    if settings.collector_sources.rss:
        tasks["rss"] = safe_collect(
            "rss",
            RssCollector(
                feed_configs=settings.rss_feeds or FEED_CONFIGS,
                keywords=settings.keywords,
                fetch_count=settings.fetch_count,
            ),
        )
    if settings.collector_sources.huggingface:
        tasks["huggingface"] = safe_collect(
            "huggingface",
            HfDailyPapersCollector(fetch_count=settings.fetch_count),
        )
    if settings.collector_sources.taptap:
        tasks["taptap"] = safe_collect(
            "taptap",
            TapTapCollector(fetch_count=settings.fetch_count),
        )

    results = await asyncio.gather(*tasks.values())
    all_items = []
    for items in results:
        all_items.extend(items)
    return all_items
```

Note: `FEED_CONFIGS` (hardcoded RSS source list in `rss_sources.py`) is kept as default; if `settings.rss_feeds` is non-empty it takes precedence.

- [ ] **Step 5: Run the resilience tests**

Run: `pytest tests/test_resilience.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add collectors/utils.py main.py tests/test_resilience.py
git commit -m "refactor: share safe_collect helper between runtime and tests"
```

---

## Task 4: Add Category-Level WeCom Transaction API

**Files:**
- Modify: `pusher/wecom.py`
- Modify: `tests/test_wecom.py`

Note: `format_message()` in `pusher/wecom.py` is a pure function and remains unchanged. Only the `WeComPusher` class is modified.

- [ ] **Step 1: Write the failing push-category tests**

```python
# tests/test_wecom.py
import httpx
import pytest

from pusher.wecom import WeComPusher, WeComError


@pytest.mark.asyncio
async def test_push_category_success_returns_push_result(httpx_mock):
    webhook = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test"
    httpx_mock.add_response(url=webhook, json={"errcode": 0, "errmsg": "ok"})
    pusher = WeComPusher(webhook)

    result = await pusher.push_category(
        category="ai",
        items=[],
        period="morning",
        pushed_urls=set(),
    )

    assert result.success is True
    assert result.category == "ai"


@pytest.mark.asyncio
async def test_push_category_raises_on_business_error(httpx_mock, sample_items_v2):
    webhook = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test"
    httpx_mock.add_response(url=webhook, json={"errcode": 45009, "errmsg": "rate limited"})
    pusher = WeComPusher(webhook)

    with pytest.raises(WeComError, match="45009"):
        await pusher.push_category(
            category="ai",
            items=sample_items_v2[:1],
            period="morning",
            pushed_urls=set(),
        )


@pytest.mark.asyncio
async def test_push_category_raises_on_http_error(httpx_mock, sample_items_v2):
    webhook = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test"
    httpx_mock.add_response(url=webhook, status_code=500)

    pusher = WeComPusher(webhook)
    # HTTP error should surface — handle in caller
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_wecom.py -v`
Expected: FAIL with `AttributeError: 'WeComPusher' object has no attribute 'push_category'`

- [ ] **Step 3: Implement `PushResult`, `WeComError`, and `push_category()`**

```python
# pusher/wecom.py
from dataclasses import dataclass


@dataclass
class PushResult:
    category: str
    success: bool
    urls: list[str]
    errcode: int | None = None
    errmsg: str | None = None


class WeComError(RuntimeError):
    def __init__(self, category: str, errcode: int | None, errmsg: str | None):
        self.category = category
        self.errcode = errcode
        self.errmsg = errmsg or "unknown"
        super().__init__(f"category={category} errcode={errcode} errmsg={self.errmsg}")


class WeComPusher:
    async def push_category(self, category, items, period="morning", pushed_urls=None) -> PushResult:
        if pushed_urls is None:
            pushed_urls = set()

        msg = format_message(items, category, period=period, pushed_urls=pushed_urls)
        payload = {"msgtype": "markdown", "markdown": {"content": msg}}
        urls = [item.url for item in items if item.url]

        client = self._client or httpx.AsyncClient()
        try:
            resp = await client.post(self.webhook_url, json=payload, timeout=15.0)
            resp.raise_for_status()
            body = resp.json()
            if body.get("errcode") != 0:
                raise WeComError(category=category, errcode=body.get("errcode"), errmsg=body.get("errmsg"))
            return PushResult(category=category, success=True, urls=urls, errcode=0, errmsg=body.get("errmsg"))
        finally:
            if self._client is None:
                await client.aclose()
```

- [ ] **Step 4: Keep old `push()` as compatibility wrapper (optional)**

```python
# Optional compatibility wrapper in pusher/wecom.py
async def push(self, items_by_category, period="morning", pushed_urls=None):
    results = []
    for category in ("ai", "game", "device"):
        cat_items = items_by_category.get(category, [])
        if not cat_items:
            continue
        results.append(await self.push_category(category, cat_items, period=period, pushed_urls=pushed_urls))
    return results
```

Use this only as a compatibility bridge. New orchestration must call `push_category()` directly.

- [ ] **Step 5: Run WeCom tests**

Run: `pytest tests/test_wecom.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pusher/wecom.py tests/test_wecom.py
git commit -m "feat: add category-level wecom push transactions"
```

---

## Task 5: Rework `main.py` Orchestration for Locking and Partial Success

**Files:**
- Create: `tests/test_main.py`
- Modify: `main.py`

- [ ] **Step 1: Write the failing orchestration tests**

```python
# tests/test_main.py
from pathlib import Path

import pytest

from collectors.base import HotItem


class StubPusher:
    def __init__(self, fail_category: str | None = None):
        self.fail_category = fail_category

    async def push_category(self, category, items, period="morning", pushed_urls=None):
        if category == self.fail_category:
            from pusher.wecom import PushResult
            return PushResult(category=category, success=False, urls=[], errcode=45009, errmsg="rate limited")
        from pusher.wecom import PushResult
        return PushResult(category=category, success=True, urls=[item.url for item in items], errcode=0, errmsg="ok")


@pytest.mark.asyncio
async def test_successful_categories_are_committed_even_if_later_one_fails(tmp_path: Path, monkeypatch):
    from main import run_push_sequence
    from infra.storage.state_store import StateStore

    grouped = {
        "ai": [HotItem("AI", "https://a.com/1", "", "qbitai", "ai", 5.0)],
        "game": [HotItem("Game", "https://g.com/1", "", "yystv", "game", 5.0)],
        "device": [HotItem("Device", "https://d.com/1", "", "ithome", "device", 5.0)],
    }
    store = StateStore(tmp_path)

    await run_push_sequence(
        grouped=grouped,
        period="morning",
        pushed_urls=store.load_pushed_urls(),
        state_store=store,
        pusher=StubPusher(fail_category="device"),
    )

    saved = store.load_pushed_urls()
    assert "https://a.com/1" in saved
    assert "https://g.com/1" in saved
    assert "https://d.com/1" not in saved
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_main.py -v`
Expected: FAIL with `ImportError` or missing `run_push_sequence`

- [ ] **Step 3: Extract orchestration into a testable helper**

```python
# main.py
async def run_push_sequence(grouped, period, pushed_urls, state_store, pusher):
    current_urls = set(pushed_urls)
    for category in ("ai", "game", "device"):
        cat_items = grouped.get(category, [])
        if not cat_items:
            continue

        result = await pusher.push_category(
            category=category,
            items=cat_items,
            period=period,
            pushed_urls=current_urls,
        )

        if result.success:
            current_urls = state_store.merge_pushed_urls(set(result.urls))
            state_store.write_daily_digest_category(
                period=period,
                category=category,
                items=[
                    {
                        "title": item.title,
                        "url": item.url,
                        "summary": item.summary,
                        "source": item.source,
                        "score": item.source_score,
                    }
                    for item in cat_items
                ],
            )
        else:
            logger.error(
                "push failed for category=%s errcode=%s errmsg=%s",
                result.category,
                result.errcode,
                result.errmsg,
            )
    return current_urls
```

- [ ] **Step 4: Add task lock and run_id in `main()`**

```python
# main.py
import uuid
import portalocker

# Generate run_id for log correlation
run_id = uuid.uuid4().hex[:8]

# Acquire task lock before collection starts
lock_path = DATA_DIR / ".task.lock"
lock_path.parent.mkdir(parents=True, exist_ok=True)
lock_fd = open(lock_path, "w", encoding="utf-8")
try:
    portalocker.lock(lock_fd, portalocker.LOCK_EX | portalocker.LOCK_NB)
except portalocker.LockException:
    logger.warning("已有任务实例运行中，退出")
    sys.exit(0)

# Configure logging with run_id
logging.basicConfig(
    level=logging.INFO,
    format=f"%(asctime)s %(levelname)s [{run_id}]: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(today_dir / "daily.log", encoding="utf-8"),
    ],
)
```

Lock acquisition must happen after logging is initialized but before collection starts.

- [ ] **Step 5: Wire `main()` to use `Settings`, `StateStore`, and `run_push_sequence()`**

```python
# main.py
settings = Settings.load(CONFIG_PATH)
settings.validate_for_run(dry_run=dry_run)
state_store = StateStore(DATA_DIR)
pushed_urls = state_store.load_pushed_urls()

grouped = merger.merge(all_items, period=period)

if dry_run:
    ...
else:
    pusher = WeComPusher(settings.wecom_webhook)
    await run_push_sequence(
        grouped=grouped,
        period=period,
        pushed_urls=pushed_urls,
        state_store=state_store,
        pusher=pusher,
    )
    cleanup_old_digests()
```

- [ ] **Step 6: Run orchestration tests**

Run: `pytest tests/test_main.py tests/test_state_store.py tests/test_wecom.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: orchestrate category-level push commits with task locking"
```

---

## Task 6: Add Packaging, Tooling, and Local Workflow Commands

**Files:**
- Create: `pyproject.toml`
- Create: `Makefile`
- Create: `.env.example`
- Modify: `.gitignore`
- Modify: `requirements.txt`

- [ ] **Step 1: Write the failing install contract check**

Create a manual verification note in the plan and use it as the acceptance gate:

```bash
python3 -m venv /tmp/claw-news-plan-check
source /tmp/claw-news-plan-check/bin/activate
pip install -e ".[dev]"
```

Expected before implementation: FAIL because `pyproject.toml` does not exist.

- [ ] **Step 2: Add `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "claw-news"
version = "0.2.0"
description = "Daily hot-news aggregation and WeCom push"
requires-python = ">=3.11"
readme = "README.md"
dependencies = [
  "httpx>=0.27.0",
  "beautifulsoup4>=4.12.0",
  "feedparser>=6.0.0",
  "pyyaml>=6.0",
  "curl-cffi>=0.7.0",
  "deep-translator>=1.11.0",
  "portalocker>=2.0",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.0.0",
  "pytest-asyncio>=0.24.0",
  "pytest-httpx>=0.30.0",
  "ruff>=0.8.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "W"]
```

- [ ] **Step 3: Add `Makefile`, `.env.example`, and `.gitignore` updates**

```makefile
.PHONY: install test lint format run-morning run-evening dry-run clean clean-data

install:
	python3 -m venv venv
	./venv/bin/pip install -e ".[dev]"

test:
	./venv/bin/pytest -v

lint:
	./venv/bin/ruff check .

format:
	./venv/bin/ruff format .

run-morning:
	./venv/bin/python main.py --period morning

run-evening:
	./venv/bin/python main.py --period evening

dry-run:
	./venv/bin/python main.py --period morning --dry-run

clean:
	rm -rf venv/ .pytest_cache/ .ruff_cache/ __pycache__/
	find . -type d -name __pycache__ -exec rm -rf {} +

clean-data:
	rm -rf data/
```

```dotenv
# .env.example
PUSHER_WECOM_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY_HERE
```

```gitignore
.env
.ruff_cache/
data/.task.lock
```

- [ ] **Step 4: Update `requirements.txt`**

Keep `requirements.txt` for open-source dependency visibility. Sync runtime deps from `pyproject.toml`:

```text
httpx>=0.27.0
beautifulsoup4>=4.12.0
feedparser>=6.0.0
pyyaml>=6.0
curl-cffi>=0.7.0
deep-translator>=1.11.0
portalocker>=2.0
```

Primary install entry remains `pip install -e ".[dev]"`; `requirements.txt` is a compatibility reference.

- [ ] **Step 5: Verify the install and local workflow contract**

Run:

```bash
make install
make lint
make test
```

Expected:

- `make install` completes without packaging errors
- `make lint` exits 0
- `make test` exits 0

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml Makefile .env.example .gitignore requirements.txt
git commit -m "chore: add packaging and local workflow tooling"
```

---

## Task 7: Add CI, Documentation, and Deploy Template

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `deploy.example.sh`
- Modify: `README.md`

- [ ] **Step 1: Add the CI workflow**

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - run: pip install -e ".[dev]"
      - run: ruff format --check .
      - run: ruff check .
      - run: pytest -v
```

- [ ] **Step 2: Create `deploy.example.sh`**

```bash
#!/bin/bash
# Claw_news 部署模板
# 用法: bash deploy.example.sh
#
# 此脚本只做环境安装和 dry-run 验证，不会触发真实推送。
# 如需真实推送，请手动执行: ./venv/bin/python main.py --period morning
#
# 依赖:
#   - Python 3.11+
#   - 已配置 config.yaml 或 PUSHER_WECOM_WEBHOOK 环境变量

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}[1/3] 安装依赖...${NC}"
python3 -m venv venv
./venv/bin/pip install -e ".[dev]"

echo -e "${GREEN}[2/3] 运行测试...${NC}"
./venv/bin/pytest -v

echo -e "${YELLOW}[3/3] 验证 dry-run...${NC}"
./venv/bin/python main.py --period morning --dry-run

echo -e "${GREEN}部署验证完成。${NC}"
echo -e "${YELLOW}如需真实推送，请手动执行: ./venv/bin/python main.py --period morning${NC}"
```

- [ ] **Step 3: Update README to match the new contract**

Add or revise the following sections:

```markdown
## Quick Start

```bash
make install
make test
cp .env.example .env
# 编辑 .env 填入你的 webhook，或直接在 shell 中 export:
export PUSHER_WECOM_WEBHOOK="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY_HERE"
make dry-run
```

Notes:
- `.env.example` is a template only; the app does NOT auto-load `.env`. You must export the env var or configure it in your launcher (launchd/cron/shell).
- `--dry-run` does not require a webhook
- `make clean` does not remove runtime state (`data/`)
- `make clean-data` removes `data/` (pushed_urls, daily digests, logs)
```

Also:
- Remove obsolete `ithome.py` references from the project tree
- Update file tree to reflect new `infra/` directory

- [ ] **Step 4: Run doc and workflow verification**

Run:

```bash
make dry-run
```

Expected:

- CLI starts without config-contract surprises
- README instructions match actual commands
- `deploy.example.sh` only performs dry-run

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml deploy.example.sh README.md
git commit -m "docs: align ci, readme, and deploy safety"
```

---

## Spec Coverage Check

| Spec Item | Covered By |
|---|---|
| M1 webhook/env validation | Task 1 |
| M1 partial-success state commit | Tasks 2, 4, 5 |
| M1 errcode validation | Task 4 |
| M1 task lock | Task 5 |
| M1 run_id in logs | Task 5 |
| M1 deploy hardening | Task 7 (`deploy.example.sh`) |
| M1 collector config injection (3 collectors) | Tasks 1, 3 |
| M1 `format_message()` unchanged | Task 4 note |
| M2 packaging/tooling | Task 6 |
| M2 CI | Task 7 |
| M2 README alignment | Task 7 |
| M2 test-contract cleanup | Tasks 3, 6 |
| M2 requirements.txt retained | Task 6 |

No spec sections are intentionally deferred inside M1/M2 scope.

---

## Final Verification Sequence

Run the full sequence after all tasks complete:

```bash
make install
make lint
make format
make test
make dry-run
```

Expected:

- editable install works in a clean environment
- lint returns zero errors
- format returns zero diffs
- pytest completes without async warning noise
- dry-run prints messages and exits without requiring a live webhook

Additional manual verification:

```bash
./venv/bin/python main.py --period morning
```

Expected:

- invalid/missing live webhook fails fast before push
- second concurrent process exits with warning
- category-level partial success writes only successful URLs
