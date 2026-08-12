# Ingest 源指标与自适应抓取开发计划

**目标**

- 为每个 source 记录抓取效果指标
- 在入池前做增量去重和基础质量过滤
- 基于最近一段时间的有效新增率与选中率，动态调整各 source 的 `fetch_count`

**范围**

- 本次只做 ingest 侧的指标、状态、准入和抓取深度调整
- 不改发布摘要的核心业务目标
- 不在本轮引入新的外部服务、数据库或复杂调度系统

**技术栈**

- Python 3.13
- FastAPI
- APScheduler
- JSON / JSONL 文件存储
- pytest

---

## 开发与检视契约

### 范围冻结

- 开发范围仅限本计划中定义的目标、文件范围和实现清单。
- 检视不会自动授权新功能、顺手重构或架构扩展。
- 开发或检视中发现的新想法，默认记为后续项，不并入当前实现。

### 文档规则

- 本计划及本任务相关文档默认只写中文版。
- 英文仅在确有必要时作为补充，不作为主版本。

### 工作区规则

- 不把直接在 `main` 上开发当作默认选项。
- 多文件改动、功能开发、需要多轮 review 的工作，优先使用隔离分支或 worktree。
- 当前任务已切到分支 `feat/ingest-source-metrics-adaptive-fetch`，后续在该分支继续。

### 检视边界

- 规格检视只检查“是否按计划实现”，不做范围扩张。
- 代码质量检视只检查正确性、可维护性、测试质量，不引入新需求。
- 如果检视发现更好的方向，需要先更新计划，再决定是否开发。

### 完成标准

- 计划内行为已实现
- 计划内测试通过
- 检视通过且未扩大范围

---

## 文件范围

**修改**

- `app/scheduler/jobs.py`
- `collectors/rss_sources.py`
- `collectors/huggingface.py`
- `app/pipeline/news_pipeline.py`
- `app/storage/ingestion_store.py`
- `tests/test_ingest_job.py`
- `tests/test_rss_collector.py`
- `tests/test_huggingface.py`
- `tests/test_app_api.py`

**新增**

- `app/storage/source_metrics_store.py`
- `app/storage/source_state_store.py`
- `app/ingest/source_policy.py`
- `tests/test_source_metrics_store.py`
- `tests/test_source_state_store.py`

---

## 指标定义

每轮每个 source 记录一条 metric，核心字段如下：

- `source`
- `run_id`
- `run_started_at`
- `raw_fetched_count`
- `deduped_new_count`
- `accepted_count`
- `selected_count`
- `rejected_duplicate_count`
- `rejected_quality_count`
- `duration_ms`
- `status`

派生指标：

- `effective_new_rate = accepted_count / raw_fetched_count`
- `selection_rate = selected_count / accepted_count`

---

## 开发实现清单

### 任务 1：Source 指标存储

目标：

- 新增 `SourceMetricsStore`
- 支持写入单轮 source metric
- 支持按天读取 metric
- 支持按 source 聚合最近窗口，计算 `effective_new_rate` 和 `selection_rate`

文件：

- `app/storage/source_metrics_store.py`
- `tests/test_source_metrics_store.py`

状态：

- 已完成实现
- 已通过本地测试
- 已通过规格检视
- 已通过代码质量检视，可视为完成

### 任务 2：Source 自适应状态存储

目标：

- 新增 `SourceStateStore`
- 持久化每个 source 的：
  - 当前 `fetch_count`
  - `min_fetch_count`
  - `max_fetch_count`
  - `cooldown_remaining`
  - `last_adjusted_at`

文件：

- `app/storage/source_state_store.py`
- `tests/test_source_state_store.py`

验收点：

- 缺省状态可自动补齐
- 修改后的 state 能正确落盘和读回

状态：

- 已完成实现
- 已通过本地测试
- 已通过规格检视
- 已通过代码质量检视，可视为完成

### 任务 3：质量过滤与抓取深度策略

目标：

- 新增 `app/ingest/source_policy.py`
- 实现基础准入规则：
  - title 不能为空
  - url 不能为空
  - summary 过短丢弃
  - 非 AI 类候选不入 AI 候选池
- 实现抓取深度调整规则：
  - 高有效新增率且高选中率时提升 `fetch_count`
  - 长期低有效新增率时降低 `fetch_count`
  - 调整后进入冷却期，避免频繁抖动

文件：

- `app/ingest/source_policy.py`
- `tests/test_ingest_job.py`

验收点：

- 过滤规则可单测
- 调整规则可单测
- `fetch_count` 始终受最小值和最大值约束

状态：

- 已完成实现
- 已通过本地测试
- 已通过规格检视
- 已完成代码质量收口，可视为完成

### 任务 4：接入 ingest 主链路

目标：

- ingest 前加载最近已见 `canonical_key`
- source 抓取后先做写前去重
- 去重后再做质量过滤
- 每个 source 写入本轮 metric
- 基于最近窗口聚合结果更新 source state
- RSS 和 HF 的 `fetch_count` 支持运行时注入

文件：

- `app/scheduler/jobs.py`
- `app/storage/ingestion_store.py`
- `collectors/rss_sources.py`
- `collectors/huggingface.py`
- `tests/test_ingest_job.py`
- `tests/test_rss_collector.py`
- `tests/test_huggingface.py`

验收点：

- 重复内容不再重复入池
- 低质量内容不会入池
- 每轮 source metric 被记录
- `fetch_count` 会读取 source state

状态：

- 已完成实现
- 已通过本地测试
- 已完成收口，可视为完成

### 任务 5：把发布结果回写到 source metrics

目标：

- 发布链路完成后，按 source 统计本轮 `selected_count`
- 将选中结果回写到最近一轮对应 source metric
- 后续 rolling window 聚合时可以计算 `selection_rate`

文件：

- `app/pipeline/news_pipeline.py`
- `app/storage/source_metrics_store.py`
- `tests/test_source_metrics_store.py`
- `tests/test_app_api.py`

验收点：

- 每个 source 的 `selected_count` 能被正确回写
- 聚合结果中的 `selection_rate` 正确

状态：

- 已完成实现
- 已通过本地测试
- 已完成收口，可视为完成

---

## 验证清单

先跑聚焦测试：

```bash
./venv/bin/python -m pytest \
  tests/test_source_metrics_store.py \
  tests/test_source_state_store.py \
  tests/test_ingest_job.py \
  tests/test_rss_collector.py \
  tests/test_huggingface.py \
  tests/test_app_api.py -q
```

再跑全量测试：

```bash
./venv/bin/python -m pytest -q
```

---

## 后续项记录规则

以下内容如果在开发或检视中出现，只记录，不直接开发：

- missed ingest 的补偿抓取
- source 级失败降级策略
- source 指标可视化或 health 展示增强
- 更细粒度的 source 专属质量规则
- GitHub source 是否纳入候选池和动态抓取策略
