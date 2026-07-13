# 内容池治理验收前纠正实施计划

> **给开发 AI：** 每个任务使用全新开发 AI；完成后依次进行 spec compliance review 与 code quality review。任务级 commit 须经主审核 AI 批准；push、merge、deploy 或真实推送仍须用户明确批准。

**目标：** 清除进入 Task 8 前的质量门禁与验收资产缺口，使最终验收可复现、脱敏且有完整运维入口。

**架构：** 纠正 Task A 仅修复 Ruff 风格问题；纠正 Task B 补齐 Task 7 漏交的合成回放样本、场景断言、运维入口与完成状态；纠正 Task C 为合成样本增加人工相关性标注证据。三者均不改变选材、评分、过滤、采集或发布语义。

**技术栈：** Python 3.11+、pytest、Ruff、YAML、Markdown。

## 全局约束

1. 先完整阅读 `AGENTS.md`、当前任务、设计第 14 与 15.3 节及相关现有代码。
2. 文档中文优先；不得写入生产候选原文、密钥、webhook、机器绝对路径或生产状态副本。
3. 不得修改 `app/pipeline/selection.py`、`app/pipeline/news_pipeline.py` 的业务语义、来源评分常量、GitHub 链路或真实推送行为。
4. 每个代码任务测试先行；纯格式修复可跳过失败测试，但必须证明仅为格式/导入排序。
5. 每个任务完成后由主审核 AI 审核完整 diff；不得自行 push、merge、deploy 或真实推送。
6. Task A 与 Task B 可并行，但不得编辑同一文件；Task 8 依赖二者都完成并审核。

---

## 纠正 Task A：全仓 Ruff 质量门禁收口

**任务元数据**

- 依赖任务：Task 1 至 Task 7
- 允许并行：纠正 Task B
- 预计修改：仅 `make lint` 当前报告的 Python 文件
- 不得修改：业务逻辑、测试断言语义、Ruff 配置、`pyproject.toml`、`Makefile`、设计常量
- 完成状态：complete（审核提交：`37966ec`）

### 1. 背景

Task 8 要求 `make lint` 与格式检查全绿；当前全仓 Ruff 有 45 项历史风格问题。Task 8 禁止直接修复缺陷，必须先独立收口。

### 2. 目标

在不改变可观察行为的前提下，让 `make lint`、`./venv/bin/ruff format --check .` 与全量 pytest 均通过。

### 3. 前置依赖

基线为 `09c075b6ef47b50faa30f344ae627259193f1743`；开始前记录 `make lint` 的完整输出及受影响文件。

### 4. 输入与输出契约

输入是 Ruff 规则 `E/F/I/W`、行宽 100 及当前违规文件。输出仅允许导入排序、换行、空白和等价语法排版；不得新增、删除或弱化断言，不得改变函数签名、返回值或控制流。

### 5. 修改范围

仅改 Ruff 实际报告的文件。对 `I001` 采用 Ruff 推荐导入顺序；对 `E501` 只拆分长表达式或字面量。若发现 `F/W`，先报告主审核 AI，不得猜测删除代码是否安全。

### 6. 禁止事项

不得增加 `# noqa`、扩大忽略规则、修改 Ruff 配置或行宽；不得把业务重构、测试重写或 Task 8 报告混入本任务。

### 7. 执行要求

先记录失败基线；每批修改后运行直接覆盖测试；逐文件审查完整 diff，证明没有语义改动。

### 8. 实施步骤

- [ ] 运行 `make lint`，按文件和规则记录实际错误数。
- [ ] 对 `I001` 使用 `./venv/bin/ruff check --fix app/github_ranking.py app/pipeline/news_pipeline.py tests/test_github_collector.py tests/test_github_ranking.py tests/test_news_pipeline.py`，逐文件审查 diff。
- [ ] 对 `E501` 手工拆行，保持参数、断言和执行顺序不变。
- [ ] 运行每个被改文件的直接覆盖测试。
- [ ] 运行全量门禁并向主审核 AI 展示完整 diff 后再 commit。

### 9. 验收标准

1. `make lint` 退出 0。
2. `./venv/bin/ruff format --check .` 退出 0。
3. `make test` 全部通过。
4. diff 不含 `noqa`、Ruff 配置豁免或业务语义修改。

### 10. 检查命令

```bash
make lint
./venv/bin/ruff format --check .
make test
git diff --check
git status --short
```

### 11. 交付前自检

- [ ] 已列明所有初始 Ruff 错误及处理方式。
- [ ] 未修改配置、评分、过滤或发布逻辑。
- [ ] 每个改动文件已审查完整 diff。
- [ ] lint、format、test、diff check 均有本轮证据。
- [ ] 工作区没有未归属改动。

### 12. 交付格式

按 `AGENTS.md` 固定格式，额外提供“初始错误数 → 剩余错误数”“文件/规则映射”“语义未变说明”和精确 commit；等待主审核 AI 批准。

---

## 纠正 Task B：回放验收资产、运维入口与状态收口

**任务元数据**

- 依赖任务：Task 7（`09c075b`）
- 允许并行：纠正 Task A
- 预计创建：`tests/fixtures/content_replay/` 下的合成脱敏 fixture
- 预计修改：`tests/test_content_replay.py`、`docs/operations/daily-checklist.md`、`docs/operations/troubleshooting.md`、`docs/README.md`、主实施计划
- 不得修改：生产回放实现、生产状态目录、评分/过滤/发布代码、GitHub 链路
- 完成状态：complete（审核提交：`3062986`）

### 1. 背景

Task 7 有只读回放代码，但没有受版本控制的合成历史样本，也遗漏 daily checklist、troubleshooting 与 docs index 入口。Task 8 无法可复现地覆盖三个必需场景。

### 2. 目标

提供脱敏固定 fixture，覆盖“IT之家候选多数”“AI 当日不足且仅同类跨日补位”“深度源 72 小时有效期边界”；补齐运维入口及 Task 2–7 的审核完成状态。

### 3. 前置依赖

使用既有 `run_replay(data_dir, at, lookback_hours=72) -> dict` 和 CLI，签名不得改变。Task 2–7 已审核提交分别为 `1f52d4b`、`d851a18`、`0261460`、`c232470`、`94b88f0..9f96a10`、`207a107..09c075b`。

### 4. 输入与输出契约

fixture 位于版本控制的 `tests/fixtures/content_replay/`，仅含虚构标题、`*.test` URL、固定时间和无敏感配置。每个场景有候选 JSONL、最小 feeds 配置、`expected.json`；测试在回放前后比较递归 SHA-256。结果必须能追溯来源/分类分布、今日/跨日数、拒绝原因和人工无关标记的样本标注来源。

### 5. 修改范围

创建 `ithome-majority`、`ai-backfill`、`deep-72h-boundary` 三个 fixture；增加各自断言；更新三份运维文档；在主计划中仅把 Task 2–7 状态回填为带精确 commit 的 `complete`。

### 6. 禁止事项

不得复制 `data/`、提交生产候选、Webhook、API key 或真实 URL/标题；不得改 `app/tools/content_replay.py`、CLI 参数、`SourcePolicy`、`select_digest()` 或生产 pipeline；不得把单次样本结论说成自动分级或普遍人工质量结论。

### 7. 执行要求

测试先行；fixture 必须复制到 `tmp_path` 后回放，绝不写入版本控制样本；固定时间为 `2026-07-11T09:00:00+08:00` 或场景元数据明确的等价时间；文档不得写本机绝对路径。

### 8. 实施步骤

- [ ] 新增三个 fixture 目录与 `expected.json`；候选字段符合 `CandidateItem`，策略符合 Task 2 契约。
- [ ] 在 `tests/test_content_replay.py` 先添加 fixture 复制、hash 与三场景断言，确认 fixture 缺失时失败。
- [ ] 最小化添加测试辅助函数和 fixture 文件，不修改生产回放代码；运行新增测试确认通过。
- [ ] 对三个临时副本运行 JSON/text 回放，确认退出 0 且输入 hash 不变。
- [ ] 更新 daily checklist、troubleshooting、docs index，包含命令、结果解释、只读保证、禁止提交生产数据和常见错误处理。
- [ ] 回填 Task 2–7 的完成状态；不改 Task 8 状态。
- [ ] 运行规定测试与格式检查，主审核 AI 审核完整 diff 后再 commit。

### 9. 验收标准

1. 三个合成脱敏场景均被版本控制，测试证明回放不修改输入。
2. 高频源候选多数、AI 跨日补位、深度源 72 小时边界均有独立断言。
3. 运维人员可从 `docs/README.md` 找到回放命令、只读限制和故障排查。
4. Task 2–7 均回填为有审核提交证据的 complete。
5. 未修改生产回放实现或业务语义。

### 10. 检查命令

```bash
./venv/bin/pytest tests/test_content_replay.py -v
./venv/bin/pytest tests/test_source_policy.py tests/test_time_policy.py \
  tests/test_ingestion_store.py tests/test_relevance_filter.py \
  tests/test_content_selection.py tests/test_news_pipeline.py \
  tests/test_content_replay.py -v
./venv/bin/ruff check tests/test_content_replay.py
./venv/bin/ruff format --check tests/test_content_replay.py
git diff --check
git status --short
```

### 11. 交付前自检

- [ ] 三个 fixture 均虚构、脱敏且没有生产状态副本。
- [ ] 每个场景都在临时副本上回放并比较 hash。
- [ ] 未修改任何生产实现。
- [ ] docs index、daily checklist、troubleshooting 有相互可达入口。
- [ ] 状态回填仅引用已有审核证据。
- [ ] 所有指定测试和格式检查都有实际输出。

### 12. 交付格式

按 `AGENTS.md` 固定格式，额外列出 fixture 与脱敏说明、三个场景命令/摘要、hash 证据、文档入口、回填状态和精确 commit；等待主审核 AI 批准。

---

+---

## 纠正 Task C：合成样本人工相关性标注证据

**任务元数据**

- 依赖任务：纠正 Task B（`3062986`）
- 允许并行：无
- 预计创建：`tests/fixtures/content_replay/relevance-annotations.json`
- 预计修改：`tests/test_content_replay.py`、`tests/fixtures/content_replay/ithome-majority/expected.json`、对应候选 JSONL
- 不得修改：`app/`、回放 CLI、生产状态、评分/过滤/发布代码、Task 8 验收报告
- 完成状态：pending

### 1. 背景

设计第 14 节第 12 项要求历史样本回放能够对比人工相关性评价。现有合成 fixture 能证明来源、补位和有效期，但没有版本化人工标注，Task 8 不得在验收中临时造数。

### 2. 目标

为合成样本中明确无关的高频来源候选提供可审计人工标注，并证明其被相关性过滤拒绝；为 Task 8 报告提供可复算的标注总数、拒绝数和未拒绝数。

### 3. 前置依赖

使用已提交的合成 fixture、`run_replay()` 返回的 `rejection_reasons` 与现有只读 hash 辅助。标注仅服务于固定合成样本，不得推导真实来源质量或自动分级。

### 4. 输入与输出契约

`relevance-annotations.json` 必须包含：`scenario`、`url`、`manual_label`（只允许 `obviously_irrelevant`）、`reason`（中文、说明与 AI/tool/game 无关）和 `expected_rejection_reason`。测试读取该文件，在 `tmp_path` 副本中运行回放，验证每个标注 URL 未入选且对应聚合拒绝原因存在；同时断言标注条目、URL 和标签均唯一、所有 URL 为 `.test`。

### 5. 修改范围

- 在 `ithome-majority` fixture 加入至少一条明显无关、虚构、`.test` URL 的候选；候选仍使用现有支持分类。
- 新增标注 JSON 与最小测试断言。
- 如需更新 `expected.json`，只可增加与标注有关的计数预期。

### 6. 禁止事项

- 不改相关性规则或回放实现来配合样本。
- 不使用真实标题、URL、人工身份、生产标注或敏感数据。
- 不把“明显无关”之外的主观质量判断写入标注。

### 7. 执行要求

测试先行；fixture 与标注在 `tmp_path` 副本回放；递归 SHA-256 仍须证明输入未变；记录标注数量和对应拒绝原因，不依赖当前日期或网络。

### 8. 实施步骤

- [ ] 增加标注验证测试，运行其确认缺失 fixture/标注时失败。
- [ ] 增加一条虚构明显无关的 `ithome` 候选和 `relevance-annotations.json`，使用现有 source policy 与固定时间。
- [ ] 运行回放测试，确认该 URL 未入选、标注数为 1、`expected_rejection_reason` 在回放拒绝原因中出现，且 hash 不变。
- [ ] 运行回放测试、Ruff check/format 与 `git diff --check`；主审核 AI 审核完整 diff 后再 commit。

### 9. 验收标准

1. 版本控制中存在脱敏且格式可校验的人工标注文件。
2. 每个标注 URL 都未入选，且有对应过滤拒绝原因。
3. 标注输入与回放一样只读，未修改生产代码或相关性规则。
4. Task 8 可从该文件复算人工标注的总数、拒绝数和未拒绝数。

### 10. 检查命令

```bash
./venv/bin/pytest tests/test_content_replay.py -v
./venv/bin/ruff check tests/test_content_replay.py
./venv/bin/ruff format --check tests/test_content_replay.py
git diff --check
git status --short
```

### 11. 交付前自检

- [ ] 标注中的 URL 全为 `.test`，没有真实内容或人工身份信息。
- [ ] 测试证明标注候选未入选且输入 hash 不变。
- [ ] 标注只声明明显无关，不包含来源总体质量判断。
- [ ] 未修改生产实现、规则或 Task 8 报告。

### 12. 交付格式

按 `AGENTS.md` 固定格式，额外列出标注 schema、标注计数、拒绝原因、TDD 的 RED/GREEN 证据和精确 commit；等待主审核 AI 批准。

## Task 8 启动门槛

仅在纠正 Task A、纠正 Task B 与纠正 Task C 都通过独立审核，且以下命令均通过后，才可启动原 Task 8：

```bash
make test
make lint
./venv/bin/ruff format --check .
git diff --check
```

Task 8 必须使用 Task B 的合成 fixture 回放；不得使用未版本控制的 `data/` 目录作为唯一验收样本。
