# 内容源扩充与三类正式发布 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让正式 ingest / publish 主链路稳定支持 `AI / 工具 / 游戏` 三类内容，并接入首批中文为主的新内容源。

**Architecture:** 复用现有统一 pipeline，不拆新系统。通过扩展源配置、放宽 ingest / publish 范围、收口历史 `device -> tool` 分类，并补充针对三类内容的测试，完成内容层与现有展示层的对齐。

**Tech Stack:** Python 3.12, pytest, APScheduler, httpx, feedparser, Docker Compose

## Global Constraints

- 保持当前单条 10 项摘要样式不变
- 本轮不重做评分体系
- 本轮不加入反馈体系
- 不为三类内容拆成三套独立 pipeline
- 优先接入 RSS 或稳定页面源，避免高维护成本反爬逻辑
- 中文优先，英文只保留少量高信噪比补充源
- 历史分类 `device` 必须统一收口到 `tool`
- 单源失败不得中断整轮 ingest / publish

---

## File Structure

- `collectors/ai_rss.py`
  - 现有 AI RSS 默认源与环境变量解析入口
- `collectors/rss_sources.py`
  - 通用 RSS 采集器与默认 feed 结构，需兼容 `tool / game`
- `collectors/taptap.py`
  - 现有游戏热点采集器，需接入正式 ingest 主链路
- `app/pipeline/context.py`
  - `publish_scope` 类型定义，需要从 `ai_only` 扩到三类正式发布
- `app/pipeline/news_pipeline.py`
  - 正式 publish 主链路，需要取消仅 AI 过滤并兼容三类映射
- `app/scheduler/jobs.py`
  - 正式 ingest 主链路，需要纳入三类 RSS 与 TapTap
- `tests/test_ai_rss.py`
  - AI 源配置测试
- `tests/test_rss_collector.py`
  - 通用 RSS feed 配置与分类测试
- `tests/test_ingest_job.py`
  - ingest 主链路测试
- `tests/test_main.py`
  - publish 主链路测试
- `tests/test_news_pipeline.py`
  - context / contract 相关测试
- `tests/test_data_contracts.py`
  - 数据契约与枚举类型测试

## Task 1: 扩展内容源配置并收口历史分类

**Files:**
- Modify: `collectors/ai_rss.py`
- Modify: `collectors/rss_sources.py`
- Modify: `tests/test_ai_rss.py`
- Modify: `tests/test_rss_collector.py`

**Interfaces:**
- Consumes: `load_ai_rss_feeds() -> list[dict]`, `RssCollector(feed_configs: list[dict] | None = None, ...)`
- Produces:
  - `DEFAULT_AI_RSS_FEEDS: list[dict]`
  - `DEFAULT_TOOL_RSS_FEEDS: list[dict]`
  - `DEFAULT_GAME_RSS_FEEDS: list[dict]`
  - `load_tool_rss_feeds() -> list[dict]`
  - `load_game_rss_feeds() -> list[dict]`
  - `load_all_rss_feeds() -> list[dict]`

- [ ] **Step 1: 写失败测试，约束三类默认源与 `device -> tool` 收口**

```python
def test_tool_feeds_default_to_tool_category():
    from collectors.ai_rss import load_tool_rss_feeds

    feeds = load_tool_rss_feeds()

    assert feeds
    assert all(feed["category"] == "tool" for feed in feeds)
    assert {"sspai", "ithome"} <= {feed["source"] for feed in feeds}


def test_game_feeds_include_existing_and_new_sources():
    from collectors.ai_rss import load_game_rss_feeds

    feeds = load_game_rss_feeds()

    assert {"yystv", "gamelook"} <= {feed["source"] for feed in feeds}


def test_load_all_rss_feeds_contains_ai_tool_game():
    from collectors.ai_rss import load_all_rss_feeds

    feeds = load_all_rss_feeds()
    categories = {feed["category"] for feed in feeds}

    assert categories == {"ai", "tool", "game"}
```

- [ ] **Step 2: 运行测试，确认按预期失败**

Run:
```bash
pytest tests/test_ai_rss.py tests/test_rss_collector.py -q
```

Expected:
- FAIL，提示 `load_tool_rss_feeds` / `load_game_rss_feeds` / `load_all_rss_feeds` 未定义
- 或旧断言仍期待 `device`

- [ ] **Step 3: 最小实现三类 feed 配置与环境变量解析**

```python
DEFAULT_AI_RSS_FEEDS = [
    {"url": "https://www.qbitai.com/feed", "category": "ai", "source": "qbitai"},
    {"url": "https://www.jiqizhixin.com/rss", "category": "ai", "source": "jiqizhixin"},
]

DEFAULT_TOOL_RSS_FEEDS = [
    {"url": "https://sspai.com/feed", "category": "tool", "source": "sspai"},
    {"url": "https://www.ithome.com/rss/", "category": "tool", "source": "ithome"},
]

DEFAULT_GAME_RSS_FEEDS = [
    {"url": "https://www.yystv.cn/rss/feed", "category": "game", "source": "yystv"},
    {"url": "https://www.gamelook.com.cn/feed", "category": "game", "source": "gamelook"},
]


def load_tool_rss_feeds() -> list[dict]:
    return _load_feeds("TOOL_RSS_FEEDS", "TOOL_RSS_MODE", DEFAULT_TOOL_RSS_FEEDS, "tool")


def load_game_rss_feeds() -> list[dict]:
    return _load_feeds("GAME_RSS_FEEDS", "GAME_RSS_MODE", DEFAULT_GAME_RSS_FEEDS, "game")


def load_all_rss_feeds() -> list[dict]:
    return [
        *load_ai_rss_feeds(),
        *load_tool_rss_feeds(),
        *load_game_rss_feeds(),
    ]
```

- [ ] **Step 4: 运行测试，确认源配置层通过**

Run:
```bash
pytest tests/test_ai_rss.py tests/test_rss_collector.py -q
```

Expected:
- PASS，且旧 `device` 相关断言已更新为 `tool`

- [ ] **Step 5: Commit**

```bash
git add collectors/ai_rss.py collectors/rss_sources.py tests/test_ai_rss.py tests/test_rss_collector.py
git commit -m "feat: add ai tool game feed configuration"
```

## Task 2: 扩展正式 ingest 主链路到三类内容

**Files:**
- Modify: `app/scheduler/jobs.py`
- Modify: `tests/test_ingest_job.py`

**Interfaces:**
- Consumes:
  - `load_all_rss_feeds() -> list[dict]`
  - `TapTapCollector.collect() -> list[HotItem]`
  - `hotitem_to_candidate(item, ingest_run_id: str) -> CandidateItem`
- Produces:
  - `run_ingest() -> dict`
  - `status_payload["successful_sources" | "failed_sources" | "skipped_sources"]`
  - ingest 后可写入 `ai / tool / game` 三类候选

- [ ] **Step 1: 写失败测试，约束 ingest 支持 RSS 三类与 TapTap**

```python
@pytest.mark.asyncio
async def test_run_ingest_accepts_tool_and_game_candidates(tmp_path):
    from app.scheduler.jobs import run_ingest

    rss_items = [
        HotItem("AI", "https://a.com/1", "s", "qbitai", "ai", 5.0),
        HotItem("Tool", "https://t.com/1", "s", "sspai", "tool", 5.0),
        HotItem("Game", "https://g.com/1", "s", "yystv", "game", 5.0),
    ]

    with (
        patch("app.scheduler.jobs.IngestionStore") as store_cls,
        patch("collectors.rss_sources.RssCollector") as rss_cls,
        patch("collectors.taptap.TapTapCollector") as taptap_cls,
    ):
        rss_cls.return_value.collect = AsyncMock(return_value=rss_items)
        taptap_cls.return_value.collect = AsyncMock(return_value=[])

        await run_ingest()

    saved = store_cls.return_value.append_or_merge.await_args.args[0]
    assert {item.category for item in saved} == {"ai", "tool", "game"}
```

- [ ] **Step 2: 运行测试，确认当前实现失败**

Run:
```bash
pytest tests/test_ingest_job.py -q
```

Expected:
- FAIL，原因是 `run_ingest()` 当前只保留 `item.category == "ai"`，且未调用 `TapTapCollector`

- [ ] **Step 3: 最小实现 ingest 三类接入**

```python
from collectors.ai_rss import load_all_rss_feeds
from collectors.taptap import TapTapCollector

collector_specs = [
    ("rss", RssCollector, {"feed_configs": load_all_rss_feeds()}),
    ("huggingface", HfDailyPapersCollector, {"proxy": hf_proxy}),
    ("taptap", TapTapCollector, {}),
]

allowed_categories = {"ai", "tool", "game"}

raw_items = [i for i in items if i.category in allowed_categories]
```

- [ ] **Step 4: 运行 ingest 测试，确认三类内容写入且单源容错仍在**

Run:
```bash
pytest tests/test_ingest_job.py -q
```

Expected:
- PASS
- 原有 “单源失败不影响整轮” 用例继续通过

- [ ] **Step 5: Commit**

```bash
git add app/scheduler/jobs.py tests/test_ingest_job.py
git commit -m "feat: ingest ai tool game sources"
```

## Task 3: 扩展 publish scope 并放宽正式发布范围

**Files:**
- Modify: `app/pipeline/context.py`
- Modify: `app/pipeline/news_pipeline.py`
- Modify: `tests/test_news_pipeline.py`
- Modify: `tests/test_data_contracts.py`
- Modify: `tests/test_main.py`

**Interfaces:**
- Consumes:
  - `RunContext(publish_scope=...)`
  - `Merger(top_n=10).merge(...)`
  - `render_digest(summary, github_items=...)`
- Produces:
  - `PublishScope = Literal["ai_only", "all_digest"]`
  - `RunContext.publish_scope` 默认兼容旧值
  - `run_pipeline()` 在 `all_digest` 下允许 `ai / tool / game`

- [ ] **Step 1: 写失败测试，约束 `publish_scope` 新值与三类发布**

```python
def test_run_context_supports_all_digest_scope():
    from app.pipeline.context import RunContext

    ctx = RunContext(trigger_mode="http", publish_scope="all_digest")

    assert ctx.publish_scope == "all_digest"


@pytest.mark.asyncio
async def test_all_digest_scope_keeps_tool_and_game_candidates(tmp_path):
    from app.pipeline.news_pipeline import run_pipeline

    config = _make_config()
    ctx = _make_ctx(publish_scope="all_digest")

    candidates = [
        _make_candidate(url="https://example.com/ai", category="ai"),
        _make_candidate(url="https://example.com/tool", category="tool", source="sspai"),
        _make_candidate(url="https://example.com/game", category="game", source="yystv"),
    ]

    with patch("app.pipeline.news_pipeline.IngestionStore") as mock_is:
        mock_is.return_value.load_window_candidates.return_value = candidates
        ...

    summarized_items = mock_llm.await_args.args[0]
    assert {item["link"] for item in summarized_items} == {
        "https://example.com/ai",
        "https://example.com/tool",
        "https://example.com/game",
    }
```

- [ ] **Step 2: 运行测试，确认当前只支持 `ai_only` 因而失败**

Run:
```bash
pytest tests/test_news_pipeline.py tests/test_data_contracts.py tests/test_main.py -q
```

Expected:
- FAIL，`Literal["ai_only"]` 不接受 `all_digest`
- 或 publish 仍过滤掉 `tool / game`

- [ ] **Step 3: 最小实现 scope 扩展与发布过滤放宽**

```python
PublishScope = Literal["ai_only", "all_digest"]

if ctx.publish_scope == "ai_only":
    candidates = [item for item in candidates if item.category == "ai"]
elif ctx.publish_scope == "all_digest":
    candidates = [item for item in candidates if item.category in {"ai", "tool", "game"}]
```

- [ ] **Step 4: 运行 publish / contract 测试，确认兼容旧入口并支持三类**

Run:
```bash
pytest tests/test_news_pipeline.py tests/test_data_contracts.py tests/test_main.py -q
```

Expected:
- PASS
- 旧 `ai_only` 测试仍通过
- 新 `all_digest` 测试通过

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/context.py app/pipeline/news_pipeline.py tests/test_news_pipeline.py tests/test_data_contracts.py tests/test_main.py
git commit -m "feat: allow all-digest publish scope"
```

## Task 4: 校准三类摘要映射与回归验证

**Files:**
- Modify: `app/pipeline/news_pipeline.py`
- Modify: `tests/test_main.py`
- Modify: `tests/test_wecom_markdown_renderer.py`

**Interfaces:**
- Consumes:
  - `_display_category_for(candidate) -> str`
  - `_topic_label_for(candidate) -> str | None`
  - `SummaryItem(display_category=..., topic_label=..., source=...)`
- Produces:
  - `device/tool/game/ai` 在最终摘要中稳定映射到 `AI / 工具 / 游戏`
  - 单条摘要继续维持 10 项上限与来源展示

- [ ] **Step 1: 写失败测试，约束工具与游戏落位稳定**

```python
@pytest.mark.asyncio
async def test_all_digest_renders_ai_tool_game_sections(tmp_path):
    from app.pipeline.news_pipeline import run_pipeline

    config = _make_config()
    ctx = _make_ctx(publish_scope="all_digest")

    ai_candidate = _make_candidate(url="https://example.com/ai", category="ai")
    tool_candidate = _make_candidate(url="https://example.com/tool", category="tool", source="sspai")
    game_candidate = _make_candidate(url="https://example.com/game", category="game", source="yystv")

    ...

    pushed_markdown = mock_pusher.push_single_markdown.await_args.args[0]
    assert "【AI】1" in pushed_markdown
    assert "【工具】1" in pushed_markdown
    assert "【游戏】1" in pushed_markdown
```

- [ ] **Step 2: 运行测试，确认分类映射仍不完整时失败**

Run:
```bash
pytest tests/test_main.py tests/test_wecom_markdown_renderer.py -q -k 'not PushSingleMarkdown'
```

Expected:
- FAIL，若 `tool / game` 未稳定落位或被错误映射到 `AI`

- [ ] **Step 3: 最小实现三类映射收口**

```python
def _display_category_for(candidate) -> str:
    if candidate is None:
        return "AI"
    if candidate.category == "game":
        return "游戏"
    if candidate.category in {"tool", "device"}:
        return "工具"
    if candidate.topic == "developer_tooling" or candidate.source == "github":
        return "工具"
    return "AI"
```

- [ ] **Step 4: 运行摘要相关测试与目标回归集**

Run:
```bash
pytest tests/test_main.py tests/test_news_pipeline.py tests/test_data_contracts.py tests/test_ingest_job.py tests/test_ai_rss.py tests/test_rss_collector.py tests/test_wecom_markdown_renderer.py -q -k 'not PushSingleMarkdown'
```

Expected:
- PASS
- 三类内容从 ingest 到 publish 的关键链路测试全部通过

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/news_pipeline.py tests/test_main.py tests/test_wecom_markdown_renderer.py
git commit -m "test: verify ai tool game digest mapping"
```

## Self-Review

### Spec coverage

- 三类源配置：Task 1
- `device -> tool` 收口：Task 1, Task 4
- ingest 纳入三类与 TapTap：Task 2
- publish 从 `ai_only` 扩到三类：Task 3
- 摘要保持 `AI / 工具 / 游戏` 落位：Task 4
- 单源失败不影响整体：Task 2 回归验证

### Placeholder scan

- 无 `TBD` / `TODO`
- 每个任务都给出实际文件、测试命令、期望结果、最小代码骨架

### Type consistency

- `PublishScope` 统一使用 `"ai_only" | "all_digest"`
- feed loader 统一返回 `list[dict]`
- 允许进入正式链路的 category 统一为 `ai | tool | game`

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-08-content-source-expansion.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
