# 内容候选池与选材治理验收报告

## 结论

**结论：`passed_with_notes`。**

本轮在版本控制的脱敏合成 fixture 临时副本中完成三场景回放；指定功能测试、全量测试、Ruff lint 与 format 检查均通过，且回放前后 fixture 输入哈希一致。十二条设计验收标准均有本轮命令或精确测试覆盖。结论保留 notes 的原因是：样本为合成、脱敏的历史结构回放，不能替代真实生产候选的长期统计；另需主调度 AI 按 Task 8 运行独立的 spec compliance review 与 code quality review，审查结论不得预先视为通过。

## 验收版本与方法

- 验收基线 commit：`c4d7076309324287cb3370c714bda425d6ec8742`（`test: add synthetic relevance annotations`）。
- 分支：`feature/content-pool-governance-task7`。
- 回放时刻：`2026-07-11T09:00:00+08:00`；最大回看：72 小时。
- 样本：`tests/fixtures/content_replay/` 中的 `ithome-majority`、`ai-backfill`、`deep-72h-boundary`，以及 `relevance-annotations.json`。
- 隔离方式：每个场景先复制至临时目录，再以 `scripts/replay-content-selection.py --data-dir data --at ... --format json` 回放；没有使用未版本控制的 `data/`，没有真实推送，也没有写入生产状态或 fixture。
- 只读证据：三个临时副本的递归 SHA-256 聚合哈希在运行前后均相同。

## 配置快照与样本时间窗

| 场景 | 候选时间窗 | 来源策略摘要 |
|---|---|---|
| `ithome-majority` | 2026-07-11 08:00 +08:00 | `ithome`: `fast_news/24h/2.0/strict`；其余 `qbitai`、`sspai`、`yystv`: `vertical/48h/3.5/standard` |
| `ai-backfill` | 2026-07-10 08:00 至 2026-07-11 08:00 +08:00 | `qbitai`、`sspai`、`yystv`: `vertical/48h/3.5/standard` |
| `deep-72h-boundary` | 2026-07-08 08:54 至 10:00 +08:00 | `gcores`: `deep/72h/4.0/lenient` |

## 回放分布与人工标注

“输入候选”是选材前的去重候选分布；“最终选材”是回放结果的 `selected` 分布。

| 场景 | 输入候选：来源 / 分类 | 最终选材：来源 / 分类 | 关键结果 |
|---|---|---|---|
| `ithome-majority` | 16；来源：ithome 9、qbitai 3、sspai 2、yystv 2；分类：AI 3、工具 11、游戏 2 | 10；来源：ithome 3、qbitai 3、sspai 2、yystv 2；分类：AI 3、工具 5、游戏 2 | ithome 从候选多数（9/16）降为最终 3/10；今日入选 10，补位 0 |
| `ai-backfill` | 8；来源：qbitai 3、sspai 3、yystv 2；分类：AI 3、工具 3、游戏 2 | 7；来源：qbitai 3、sspai 2、yystv 2；分类：AI 3、工具 2、游戏 2 | 今日入选 6；AI 历史补位 1；历史工具候选未进入自由竞争 |
| `deep-72h-boundary` | 3；来源：gcores 3；分类：AI 3 | 2；来源：gcores 2；分类：AI 2 | 恰好 72 小时与 72 小时内各入选 1；超过边界 1 条以 `expired` 拒绝；补位 2 |

人工相关性标注来自 `relevance-annotations.json`：总数 **1**，已拒绝 **1**，未拒绝 **0**。唯一标注为合成 `.test` URL，标签为 `obviously_irrelevant`，回放拒绝原因是 `negative_rule`；该 URL 不在最终入选列表。

## 设计第 14 节验收证据

| # | 设计验收项 | 本轮证据 | 结果 |
|---:|---|---|---|
| 1 | ithome 多数候选不凭数量占最终多数 | `test_replay_fixture_ithome_candidate_majority_is_not_final_majority`；回放 9/16 → 3/10 | 通过 |
| 2 | 明显无关高频资讯不得入选 | `test_replay_fixture_manual_relevance_annotations_are_rejected_read_only`；人工标注 1/1 被 `negative_rule` 拒绝 | 通过 |
| 3 | 今日充足时满足 AI 3、工具 2、游戏 2 | `test_category_minimums_3_2_2`；`ithome-majority` 回放为 3/5/2 | 通过 |
| 4 | 当日不足可从仍有效 48/72h 内容补位 | `test_replay_fixture_ai_history_only_fills_ai_minimum`；`ai-backfill` 回放补 AI 1 条 | 通过 |
| 5 | 跨日只补分类最低目标 | `test_historical_items_only_fill_category_deficit`；fixture 断言 `old-tool` 不入选 | 通过 |
| 6 | 已发布、过期、相关性不合格不入选 | `test_recent_loader_filters_pushed_urls_and_keys`、`test_source_retention_filters_independently`、标注拒绝测试；deep 场景 `expired: 1` | 通过 |
| 7 | 单源惩罚跨三阶段累计 | `test_source_counts_accumulate_across_phases` | 通过 |
| 8 | 原始候选保留 7 天，过期仍可审计不可推送 | `test_run_ingest_cleanup_prunes_at_7_days`、`test_filter_rejects_items_without_effective_time`、`test_source_retention_filters_independently` | 通过 |
| 9 | 完整发布时间按小时；缺失按契约回退 | `test_freshness_boundaries`、`test_effective_time_uses_published_at`、`test_effective_time_falls_back_to_fetched_at`、72h 边界回放 | 通过 |
| 10 | 过滤、补位、入选均可解释 | `test_selection_result_has_evidence`、`test_filter_rejection_audit_has_required_fields`；回放包含 `rejection_reasons` 与 `selected` | 通过 |
| 11 | 旧配置按默认值兼容 | `test_missing_policy_uses_conservative_default`、`test_resolve_unknown_source_uses_default` | 通过 |
| 12 | 回放对比来源/分类/人工相关性 | 三个 fixture 回放分布表；`relevance-annotations.json` 及标注拒绝测试 | 通过 |

## 执行检查

| 命令 | 结果 |
|---|---|
| `./venv/bin/pytest tests/test_source_policy.py tests/test_time_policy.py tests/test_ingestion_store.py tests/test_relevance_filter.py tests/test_content_selection.py tests/test_news_pipeline.py tests/test_content_replay.py -v` | 131 passed |
| `make test` | 460 passed |
| `make lint` | `All checks passed!` |
| `./venv/bin/ruff format --check .` | `92 files already formatted` |
| `git diff --check` | 无输出，退出码 0 |
| 三个 fixture 临时副本回放 | 全部退出码 0；三个运行前后哈希均相同 |

## 两轮独立审查材料

### Spec compliance review

审查范围应仅限设计第 14、15.3 节与本报告的十二项映射：来源分布、分类保底、跨日补位、72 小时边界、相关性拒绝、只读性与旧配置默认值。不得借审查扩大到 GitHub 链路、新功能或重构。材料：本报告、三份受控 fixture、`relevance-annotations.json`、`tests/test_content_replay.py`、相关精确测试结果。

状态：**通过（PASS）**。独立审核已核对十二项映射、三场景复算、人工标注、合成样本边界和范围约束，未发现设计契约缺口。

### Code quality review

审查范围应仅限回放 CLI 的无写入路径、fixture 复制与哈希证明、错误语义、测试可信度、报告的证据真实性和范围边界。材料：本报告、`scripts/replay-content-selection.py`、`app/tools/content_replay.py`、`tests/test_content_replay.py`、完整验证结果。

状态：**通过（APPROVED）**。独立审核已核对回放无写入路径、fixture 版本控制与 hash 证明、错误语义、测试可信度、报告数据和 Task 8 范围，未发现阻断问题。

## 失败项、未验证项与残留风险

- 失败项：无。
- 未验证项：无。
- 残留风险：本轮固定样本为合成和脱敏数据，能稳定验证候选结构、边界和拒绝语义，但不能量化真实生产来源在长期运行中的实际分布改善或误拒绝率。
- 后续项：在获得真实生产数据的合规脱敏与明确授权后，可另建独立验收任务，以同一报告字段复核长期来源/分类分布；不得据此自动调整 source policy。

## 范围与安全声明

本 Task 只新增本验收报告；未修改业务代码、测试、fixture、已批准常量、生产状态、GitHub 链路或真实推送配置。未执行 commit、push、merge、deploy 或真实推送。
