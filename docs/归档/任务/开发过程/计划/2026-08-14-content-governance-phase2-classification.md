# 内容治理 Phase 2 - 分类治理实施任务

**任务编号：** CG-P2-01  
**依赖任务：** 内容治理 Phase 1（`5cdb447`）  
**允许并行任务：** 无；来源扩展任务必须等待四分类契约落地  
**预计修改文件：** `app/category_policy.py`、`app/classifiers/`、`app/pipeline/selection.py`、`app/ingest/ingest_job.py`、`app/tools/llm.py`、`pusher/wecom.py`、`feeds.example.yaml`、相关测试与正式架构文档  
**不得修改文件：** 投递恢复、数据库/网站 API、评分常量、Phase 3 算法  
**完成状态：** completed

## 1. 背景

Phase 1 已提供来源上限、健康基线和摘要截断，但运行时仍为 `ai/tool/game` 三分类，综合快讯源会把数码等内容归入工具，且 tool/game 没有具体主题。

## 2. 目标

落实 Phase 2 的分类治理：引入 `digital`，对综合快讯源按内容重分类，支持四类主题，补齐数码相关性规则，并保持既有流水线和配置的兼容入口。

## 3. 前置依赖

基线为 `5cdb447`；已批准设计为 `docs/计划/内容治理方案.md` 第 4、5、8 节和 `docs/架构/网站平台设计.md` 第 9、10 节。

## 4. 输入与输出契约

输入为现有 `CandidateItem`、来源默认分类和规则配置。输出分类只能是 `ai/tool/game/digital`；输入别名 `device` 规范化为 `digital`。默认分类仅为兜底，允许配置为综合快讯的来源由内容规则重分类。选材继续使用 AI 3、工具 2、游戏 2、数码 0 的最低配额。

## 5. 修改范围

修改分类、相关性、主题、入池、选材、通用摘要提示词及企业微信分类展示代码；增加覆盖正常、边界和拒绝路径的测试；更新示例配置与内容选材、来源管理、产品说明。企业微信改动仅限四分类展示与 `device` 兼容别名，不改变协议、投递恢复或错误处理；摘要改动仅限四分类描述，不改变 JSON 输出协议。来源新增、LLM relevance、指数惩罚、同主题聚合、数据库和前端均不在本任务范围。

## 6. 禁止事项

不得改变单源上限、质量权重、freshness 评分、投递恢复语义或真实运行配置；不得把来源扩展混入本任务；不得为未识别内容静默绕过相关性过滤。

## 7. 执行要求

测试先行：先新增并运行预期失败的分类、主题、动态分类和配额测试，再做最小实现。使用合成 `.test` URL 与固定时间，不读取或提交生产 `data/`。

## 8. 实施步骤

- [x] 为四分类契约、`device` 兼容别名、数码竞争配额和动态分类新增失败测试。
- [x] 实现 `digital` 分类与内容级动态分类，限制仅综合快讯源使用。
- [x] 为 tool/game/digital 增加主题桶，并为数码增加相关性正负规则。
- [x] 同步示例配置和正式中文文档。
- [x] 运行精确测试、回放、全量测试、lint、format 与 diff 检查；已完成独立代码审核。

## 9. 验收标准

1. `device` 输入输出为 `digital`，公开运行时不存在 `device`。
2. 综合快讯中的 AI、数码、工具和游戏内容可按内容归类；非综合来源保持默认类别。
3. tool/game/digital 具有非兜底主题命中路径，且无匹配时保留可解释兜底。
4. 数码不占保底名额，能够参与自由竞争；AI/工具/游戏配额不变。
5. 数码快讯噪声被相关性规则拒绝，技术数码内容可通过。
6. 所有指定检查通过，文档与示例配置同步。

## 10. 检查命令

```bash
./venv/bin/pytest tests/test_data_contracts.py tests/test_relevance_filter.py tests/test_topic_classifier.py tests/test_content_selection.py tests/test_ingest_job.py -v
./venv/bin/python scripts/replay-content-selection.py --help
make test
make lint
./venv/bin/ruff format --check .
git diff --check
```

## 11. 交付前自检

- [x] 已阅读任务、批准设计、`AGENTS.md`、正式文档和相关代码。
- [x] 只修改允许范围，未改变上限、评分和投递语义。
- [x] 新行为具有正常、边界、降级与失败路径测试。
- [x] 未吞异常或静默放行；配置未被重新硬编码为不可调整规则。
- [x] 示例配置与中文正式文档同步。
- [x] 已检查完整 diff、密钥、绝对路径和未归属改动。
- [x] 未提交、未推送、未合并，已完成独立任务级 diff 审核。

## 12. 交付格式

按 `AGENTS.md` 的十段固定格式，逐项列出设计契约、测试证据、未验证生产项、残留风险、设计冲突和范围外改动；提交前展示完整 `git diff` 给主审核 AI。
