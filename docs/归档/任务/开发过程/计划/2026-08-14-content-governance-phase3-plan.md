# 内容治理 Phase 3 实施方案

---
状态: active
最后更新: 2026-08-15
关联:
  - ../../../../计划/内容治理方案.md
  - ../../../../架构/内容选材.md
  - ../../../../架构/系统架构.md
---

## 使用边界

本文记录已批准的 Phase 3 实施任务、参数与验收边界。代码实施仍须在独立分支中测试先行；提交、合并、推送和部署遵循仓库级门禁。

Phase 3 划分为三个实现任务，严格串行：`CG-P3-01` → `CG-P3-02` → `CG-P3-03`。既有自适应抓取实现作为所有任务的回归门禁；确认不符合既定策略时，再另建修复任务，避免重复重写。

## CG-P3-01：指数化来源多样性惩罚

**任务编号：** CG-P3-01
**依赖任务：** Phase 1、Phase 2（`29757d3`）
**允许并行任务：** 无；`selection.py` 是后续聚合和补位的共同基础
**预计修改文件：** `app/config.py`、`.env.example`、`app/pipeline/selection.py`、`tests/test_app_config.py`、`tests/test_content_selection.py`、`docs/架构/内容选材.md`
**不得修改文件：** 来源质量权重、freshness、分类配额、来源上限、LLM、调度与投递代码
**完成状态：** completed（2026-08-14：已完成 profile 回放对照与轻量验收，生产启用仍需单独批准）

### 1. 背景

当前同源惩罚是线性值 `0/-1/-2/-3.5/-5`，在来源质量分接近时不足以阻止单一来源持续占用自由竞争名额。

### 2. 目标

把同源后续候选的竞争惩罚改为指数式增长，降低重复来源在自由竞争和历史竞争阶段的相对优势，不改变来源硬/软上限语义。

### 3. 前置依赖

依赖已生效的快讯源硬上限 2、其他来源软上限 3、四分类配额和 `selection_evidence` 基线。

### 4. 输入与输出契约

输入为已选中的同源数及 `SELECTION_DIVERSITY_PENALTY_PROFILE`。新增 profile 仅可为 `linear` 或 `exponential`，默认 `linear`（保持 Phase 2 行为，可立即回滚）；已确认 `exponential` 使用 `0/-1/-3/-6/-10`（第 0 至第 4 次及以上）。输出仍是 `diversity_penalty` 和 `selection_score`，`final_score` 不变。生产启用 `exponential` 必须在回放对照通过后单独批准；任何来源上限、配额或降级语义不得由本任务改变。

### 5. 修改范围

仅增加受配置选择的值表并补充精确单测和回放对照；正式文档同步 profile、回滚方式和启用门槛。

### 6. 禁止事项

不得同时调整 `quality_weight`、freshness、配额、排序键或来源上限；不得把惩罚常量散落到调用方；不得在配置无效时静默切换 profile。

### 7. 执行要求

先新增值表、跨阶段累计、硬/软上限不变和确定性排序的失败测试，再作最小实现。用固定时间和合成候选完成回放对照。

### 8. 实施步骤

1. 固化 Phase 2 基线回放结果。
2. 写入失败测试，覆盖同一来源第 0 至第 4 次入选及跨阶段累计。
3. 修改唯一惩罚函数并运行聚焦测试。
4. 运行同一份回放，比较来源分布和分类保底。
5. 更新正式文档与任务状态。

### 9. 验收标准

1. `linear` 严格保持既有值，`exponential` 的审核批准值全部精确命中，非法 profile 被明确拒绝。
2. `final_score`、快讯源硬上限、非快讯软上限和分类配额保持不变。
3. 相同输入的选材结果保持确定性。
4. 回放未出现单源增加、分类保底丢失或候选数异常减少；将 profile 切回 `linear` 可恢复 Phase 2 基线。

### 10. 检查命令

```bash
./venv/bin/pytest tests/test_content_selection.py tests/test_content_replay.py -v
./venv/bin/python scripts/replay-content-selection.py --help
make test
make lint
./venv/bin/ruff format --check .
git diff --check
```

### 11. 交付前自检

- [ ] 只改动任务允许范围。
- [ ] 已先验证新增测试失败，再完成最小实现。
- [ ] 已保留并比较实施前后回放证据。
- [ ] 未改变评分常量以外的选材语义。
- [ ] 已完成完整 diff 审核，未提交、未推送。

### 12. 交付格式

按 `AGENTS.md` 固定十段格式，附惩罚值矩阵、回放前后来源/分类分布和未验证生产项。

## CG-P3-02：同主题相似热点聚合

**任务编号：** CG-P3-02
**依赖任务：** CG-P3-01
**允许并行任务：** 无；必须在稳定的选材评分和证据模型上接入
**预计修改文件：** `app/config.py`、`.env.example`、`app/pipeline/selection.py`、`app/tools/content_replay.py`、`tests/fixtures/content_replay/`、`tests/test_app_config.py`、`tests/test_content_selection.py`、`tests/test_content_replay.py`、`docs/架构/内容选材.md`
**不得修改文件：** 分类器词表、来源质量权重、配额、LLM、调度、投递和网站 API
**完成状态：** completed（2026-08-15：工程验收与独立终审通过；真实人工标注校准登记为 `CG-P3-02-FOLLOWUP-01`，开关保持关闭）

### 1. 背景

URL 去重无法识别不同媒体对同一热点的报道，导致日报可能被同一事件刷屏。仅按 topic 去重也不可接受，因为 `developer_tooling` 等主题桶覆盖范围过宽。

### 2. 目标

以完整选材的临时结果识别“同分类、同主题且标题/链接高度相似”的重复热点，排除败者后从全候选池完整重选至收敛；最终日报不刷屏，且所有配额和来源限制仍由统一选材流程保证。

### 3. 前置依赖

依赖 Phase 2 提供的四分类与主题；依赖 CG-P3-01 固定后的竞争分和排序规则。

### 4. 输入与输出契约

输入是已完成 Phase 2 过滤与主题分类的全候选池。新增 `TOPIC_CLUSTER_ENABLED`（默认 `0`）、`TOPIC_CLUSTER_SIMILARITY_THRESHOLD=0.70`（仅在标注 fixture 校准后可启用）和 `TOPIC_CLUSTER_MAX_ROUNDS=10`。算法固定为：先运行完整 `select_digest()`；仅在临时入选集中比较类别一致且非兜底主题一致的候选；标题标准化使用 Unicode NFKC + `casefold`，英文按连续字母数字词切分，中文按连续汉字段生成重叠二元 token；URL 使用 percent-decode 后的 path，按非字母数字/汉字分段并采用同一 token 规则。只有“标题 Jaccard ≥ 阈值”或“标题 Jaccard ≥ 0.35 且 URL path Jaccard ≥ 阈值”时才建立无向相似边。每轮以相似边构造连通分量，每个分量严格按 `(selection_score DESC, published_at DESC, canonical_key ASC)` 选唯一胜者，其余成员为败者；审计保留分量胜者和所有触发边。将败者 canonical key 加入禁选集并从**全候选池**完整重跑。禁选集必须单调增长；没有新败者即收敛。达到 `TOPIC_CLUSTER_MAX_ROUNDS` 前未收敛时，以 `topic_cluster_non_convergent` 明确失败且不发布中间结果。

### 5. 修改范围

只增加配置加载、聚合纯函数、回放输出和测试；不得改变 `TopicClassifier` 规则、默认来源分类或 URL 精确去重。

### 6. 禁止事项

不得基于 topic 名直接删除候选；不得使用网络、向量数据库或 LLM 做聚类；不得在配置无效时静默启用聚合；不得在未达到收敛时发布中间选材结果。

### 7. 执行要求

测试先行覆盖：高相似同热点、高 topic 相同但低相似、不同 topic、中文/英文标题、NFKC/大小写/URL 编码、阈值边界、关闭开关、确定性平分、链式重叠（A-B、B-C）、交叉分量、最大轮次失败、多轮重选与配额/来源上限保持。新增人工标注 fixture，分别统计误聚合与漏聚合；标注集至少 200 对、四分类各至少 40 对，误聚合率不得超过 2%，漏聚合率不得超过 15%，否则不得启用开关。

### 8. 实施步骤

1. 写入本任务定义的 token 化、相似度和收敛规则，不留给实现阶段裁决。
2. 添加失败测试、人工标注 fixture 与 Phase 2 基线回放。
3. 在选材纯函数内实现“临时选择 → 排除败者 → 全量重选”的无 I/O 收敛循环。
4. 按共享审计契约记录每轮分量胜者、败者、触发边、相似度和终选。
5. 运行误聚合/漏聚合统计、边界回放及全量检查。

### 9. 验收标准

1. 同热点多源报道只保留确定的临时高分胜者，且最终结果经过全量重选。
2. 同 topic 但不同事件、不同 topic 或低相似标题不被误删。
3. 关闭开关时严格保持 CG-P3-01 的输出。
4. 每个聚合拒绝都带原因、分量胜者 canonical key、触发边、相似度、选材轮次和 token 化版本；链式重叠结果不依赖遍历顺序。
5. 回放可显示每轮候选数、聚合前后数量、拒绝分布、误聚合/漏聚合 fixture 统计。

### 10. 检查命令

```bash
./venv/bin/pytest tests/test_app_config.py tests/test_content_selection.py tests/test_content_replay.py -v
./venv/bin/python scripts/replay-content-selection.py --help
make test
make lint
./venv/bin/ruff format --check .
git diff --check
```

### 11. 交付前自检

- [ ] 配置默认关闭，阈值校验为 `(0, 1]`，且启用前已通过标注 fixture 校准。
- [ ] 不存在仅凭 topic 删除候选的路径。
- [ ] 聚合无网络调用、无 LLM 调用且结果确定。
- [ ] 拒绝证据和回放输出完整。
- [ ] 已完成完整 diff 审核，未提交、未推送。

### 12. 交付格式

按 `AGENTS.md` 固定十段格式，附相似度规则、边界样本、误聚合风险和回放数据。

## CG-P3-03：LLM 相关性淘汰与补位

**任务编号：** CG-P3-03
**依赖任务：** CG-P3-02
**允许并行任务：** 无；终选、审计和渲染必须使用已聚合的候选集
**预计修改文件：** `app/config.py`、`.env.example`、`app/tools/llm.py`、`app/pipeline/selection.py`、`app/pipeline/news_pipeline.py`、`app/tools/summary_result.py`、`app/storage/source_metrics_store.py`、`app/tools/content_replay.py`、相关测试与 `docs/架构/内容选材.md`、`docs/架构/系统架构.md`
**不得修改文件：** LLM provider HTTP 协议、来源调节阈值、分类器、投递恢复、数据库/网站 API
**完成状态：** pending（依赖已满足，尚未启动）

### 1. 背景

规则相关性过滤存在宽泛词漏放。批准设计确定复用现有摘要调用输出 `relevance`，并在淘汰后按 `final_score` 补位，不增加第二次 LLM 调用。

### 2. 目标

以可关闭的 LLM 相关性淘汰**已评分初选项**：低相关初选内容不发布，未评分补位项遵循已批准的“不重复调用 LLM”决策并被明确标记为残留风险；候选不足时正常降级但不伪造内容或 LLM 判断。

### 3. 前置依赖

依赖 CG-P3-02 已完成的候选集和审计证据，依赖现有摘要截断与 `SummaryResult` 渲染链路。

### 4. 输入与输出契约

新增 `LLM_RELEVANCE_ENABLED`（设计已定默认关闭）和 `LLM_RELEVANCE_THRESHOLD=0.50`。启用后每个初选项必须返回数值型 `relevance`；缺失、布尔、NaN、无限或越界均使本次发布失败，绝不静默视为高相关。低于阈值的项成为禁选项后，从全候选池完整重跑 CG-P3-02 选材；补位继续遵守分类保底、来源硬/软上限和聚合规则，且不再调用 LLM。补位摘要使用本地原始摘要，标记 `relevance: null`、`relevance_source: "not_scored_backfill"`，并在内部审计中记录“未评分补位风险”。最终不足目标数时沿用既有 `PublishResult.status="degraded"`，以结构化 `degradation_reasons=["llm_relevance_insufficient_candidates"]` 标记正常降级；不新增对外 status 枚举。`degradation_reasons` 是 `DigestPayload`、pending delivery `finalization` 和 publish-status JSON 的新增可选 `list[str]` 字段，缺失时按空列表读取；不复用 `errors`。若淘汰或补位改变终选集合，`daily_judgement` 改为固定且不含内容断言的“今日精选已完成相关性复核”，并记录 `daily_judgement_source="final_selection_fallback"`；未改变集合时保留 LLM 判断并记录 `initial_selection_llm`。

### 5. 修改范围

只修改配置、LLM 输出协议、终选纯函数、发布编排、digest/回放审计、测试和正式文档。保留现有 LLM 失败、投递和 pending delivery 恢复语义。

### 6. 禁止事项

不得增加第二轮 LLM 调用；不得让补位绕过硬/软上限、分类配额或聚合；不得让格式非法的 LLM 结果继续发布；不得把未评分补位描述为 LLM 已验证内容；不得将内部拒绝原因暴露到公开渲染内容。

### 7. 执行要求

先写失败测试：开关关闭兼容、prompt JSON、有效/无效 relevance、低相关禁选后的完整重选、单次调用、来源上限与配额保持、未评分补位标记、候选不足 `degraded` 原因、日报判断降级、digest/pending delivery 审计和来源指标口径隔离。所有 LLM 以 mock 驱动。

### 8. 实施步骤

1. 增加环境变量加载、校验与示例配置。
2. 扩展 prompt 和 JSON 对齐逻辑，保留逐 URL 对应关系。
3. 在选材层实现“LLM 拒绝项禁选 → 全量重选”的无 I/O 终选函数。
4. 将终选后候选用于渲染、发布指标、状态落盘和 pending delivery；在每来源最新 ingest metric 行写入 L2 初选计数 `selection_eligible_count`。新增 `write_selection_eligible_counts()`，以 source 和最新 `run_started_at` 定位同一轮 ingest 行；`aggregate_recent()` 将 `selection_rate` 定义为 `selection_eligible_count / accepted_count`。历史行缺少字段时临时回退读取既有 `selected_count`，不迁移或重写历史文件；最终发布量继续只写独立 publish metrics，避免 LLM/聚合拒绝扭曲采集调节。
5. 按共享审计契约写入初选、淘汰、重选补位、终选、未评分补位风险和正常降级证据。
6. 执行 mock 测试、回放、全量检查与 diff 审核。

### 9. 验收标准

1. 关闭开关时与 CG-P3-02 的日报内容和 LLM 协议兼容。
2. 开启后 LLM 每项相关性值被严格校验，低相关**初选项**不发布；未评分补位显式可见且不被描述为已验证。
3. 禁选后从全候选池完整重选，LLM HTTP 调用数仍为一次。
4. 补位不违反来源上限、分类保底和同主题聚合。
5. 候选不足保持既有 `degraded` 状态并包含 `llm_relevance_insufficient_candidates` 原因，不是推送失败；LLM 格式非法仍是明确失败。
6. 终选变化时不复用初选 LLM 日报判断；digest、pending delivery 和回放均能审计初选/淘汰/补位/终选。
7. 自适应抓取的 `selection_rate` 使用 `selection_eligible_count / accepted_count`，历史缺字段行按 `selected_count` 兼容读取；最终发布量继续写入独立 publish metrics；新拒绝原因不改变既有调节阈值。

### 10. 检查命令

```bash
./venv/bin/pytest tests/test_app_config.py tests/test_app_llm.py tests/test_content_selection.py tests/test_news_pipeline.py tests/test_content_replay.py tests/test_ingest_job.py -v
./venv/bin/python scripts/replay-content-selection.py --help
make test
make lint
./venv/bin/ruff format --check .
git diff --check
```

### 11. 交付前自检

- [ ] 默认关闭与旧 LLM 输出保持兼容。
- [ ] 相关性缺失或非法值不会静默放行。
- [ ] 补位不重调 LLM，受全部选材约束，且未评分风险可审计。
- [ ] `degraded` 原因与真实 LLM/投递失败可区分，不新增公共 status 枚举。
- [ ] 自适应抓取的既有调节阈值不变，且 `selection_eligible_count` 与最终发布指标隔离验证通过。
- [ ] 已完成完整 diff 审核，未提交、未推送。

### 12. 交付格式

按 `AGENTS.md` 固定十段格式，附配置矩阵、LLM mock 覆盖、初选/终选审计样例、回放对照和生产未验证项。

## 共享审计事件契约

CG-P3-02 与 CG-P3-03 保持 `selection_evidence: list[dict]` 的既有 JSON 形状，不新增列表 envelope。每个新事件自带 `schema_version: 2`，并包含 `event`、`canonical_key`、`selection_round`、`final_score`、`selection_score`、`source`、`category`、`topic`；按事件补充字段：`topic_cluster_excluded` 包含 `component_winner_canonical_key`、`trigger_edges`、`title_similarity`、`url_similarity`、`tokenizer_version`，`llm_relevance_rejected` 包含 `relevance`、`threshold`，`llm_relevance_backfill` 包含 `relevance_source`，`final_selected` 包含 `rendered`。事件顺序固定为：临时选择、聚合排除、LLM 淘汰、重选补位、终选。旧 digest 与旧 pending payload 缺失 `schema_version`、`degradation_reasons` 或新事件字段时，按 v1 已选证据和空原因列表读取，不重写历史数据；新增字段仅限内部持久化，公开 API 忽略未知字段。

## 自适应抓取验收门禁（非实施任务）

在任一 Phase 3 任务交付前，运行 `tests/test_ingest_job.py` 与 `tests/test_source_metrics_store.py`，确认既有实现仍满足：至少 12 轮样本才调节、有效新增率和 **L2 合格选材率**共同提升、低有效新增率降低、抓取数受上下界约束、6 轮冷却期防抖。CG-P3-03 必须验证新字段按 source 回写到对应 ingest 行、`selection_rate = selection_eligible_count / accepted_count`、历史缺字段行回退 `selected_count`，以及聚合/LLM 拒绝不会作为采集质量下降写回该指标；最终发布条数仅进入独立 publish metrics。若不满足，记录为 `CG-P3-FOLLOWUP-01`，另行设计和审核，不混入上述三个任务。

## 已确认参数与后续审核重点

已确认参数：指数 profile 值 `0/-1/-3/-6/-10`、聚合相似度阈值 `0.70`、最大轮次 `10`、标注门槛 `200 / 2% / 15%`、LLM relevance 阈值 `0.50`。P3-03 实施及后续审核重点包括：profile 回滚、聚合收敛上界与连通分量、token 化误伤、未评分补位风险、状态兼容、日报判断降级、审计 schema 和自适应抓取指标隔离。
