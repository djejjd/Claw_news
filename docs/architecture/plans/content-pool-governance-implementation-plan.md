# 内容候选池与选材治理实施计划

> **供 agentic workers 使用：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按 Task 执行。所有步骤使用复选框跟踪；每个 Task 使用全新的任务上下文并单独审核。

**目标：** 建立分源策略、小时级有效期、推送前相关性过滤、分类保底与跨日补位，使高频综合源不能依靠候选数量自然霸榜，同时保留完整候选证据。

**架构：** 原始候选池继续保存所有去重后的合格采集结果；发布阶段读取最多 72 小时候选，按来源策略过滤有效期，再执行跨分类相关性判断和三阶段选材。来源策略、相关性判断、时间判断和选材分别放在独立模块，`news_pipeline.py` 只负责串联。

**技术栈：** Python 3.11+、dataclasses、PyYAML、JSONL、pytest、pytest-asyncio、Ruff。

**批准设计：** `docs/architecture/decisions/content-pool-governance-design.md`

## 全局约束

1. 文档、注释和交付说明默认中文；代码标识符、命令、协议字段保持原文。
2. 不修改 GitHub 推荐链路，不引入数据库、消息队列、LLM 逐篇过滤或新线上基础设施。
3. 原始候选保留 7 天；推送有效期按源为 24、48、72 小时；最大读取范围为 72 小时。
4. 分类最低目标固定为 AI 3、工具 2、游戏 2；总数上限 10；不足时允许少发。
5. 跨日内容只用于补足分类最低目标，不参与今日自由竞争。
6. 唯一排名分数为 `final_score = source_quality_weight + freshness_score`。
7. `freshness_score` 固定为 `0-24h: 3.0`、`24-48h: 1.5`、`48-72h: 0.5`。
8. 单源惩罚固定为已入选 `0/1/2/3/4+` 条时 `0.0/-1.0/-2.0/-3.5/-5.0`，三个选材阶段累计计数。
9. 相关性 profile 门槛固定为 `strict=0.7`、`standard=0.5`、`lenient=0.3`；排除规则优先。
10. 不清空 `seen_keys`，不使用第二套 `admission_score`，不增加最终单源硬上限。
11. 每个代码 Task 必须测试先行；没有看到预期失败，不得写实现。
12. 每个 Task 只提交自己的范围；发现契约冲突立即停止并报告，不得自行扩题。

## 文件职责与依赖图

| 文件 | 职责 |
|---|---|
| `AGENTS.md` | 所有 AI 的仓库级统一开发契约 |
| `CLAUDE.md` | Claude 专属适配，并强制先读 `AGENTS.md` |
| `app/content/source_policy.py` | 来源策略类型、默认值、校验与 registry |
| `app/content/time_policy.py` | 时间解析、文章年龄、今日判断、有效期和 freshness |
| `app/classifiers/relevance_filter.py` | AI/工具/游戏相关性规则、profile 门槛和解释结果 |
| `app/pipeline/selection.py` | 三阶段选材与跨阶段单源惩罚 |
| `app/pipeline/candidate.py` | 候选数据契约和解释字段 |
| `collectors/ai_rss.py` | 从 YAML 加载并保留来源策略字段 |
| `collectors/rss_sources.py` | 保存 RSS 完整发布时间 |
| `collectors/base.py` | `HotItem` 到 `CandidateItem` 的完整时间传递 |
| `app/storage/ingestion_store.py` | 7 天保留、72 小时读取、折叠和已发布过滤 |
| `app/pipeline/news_pipeline.py` | 串联读取、策略、相关性、评分、选材和证据落盘 |
| `app/storage/source_metrics_store.py` | 按实际文章 source 写入过滤与补位聚合指标 |
| `scripts/replay-content-selection.py` | 只读历史回放，不推送、不写生产状态 |

依赖顺序：Task 1 → Task 2 → Task 3；Task 4 在 Task 2 后可与 Task 3 并行；Task 5 依赖 Task 2、3、4；Task 6 依赖 Task 5；Task 7 依赖 Task 6；Task 8 依赖全部任务。

---

## Task 1：建立仓库级多 AI 开发契约

**任务元数据**

- 依赖任务：无
- 允许并行：无，必须先完成
- 预计修改：`AGENTS.md`、`CLAUDE.md`
- 不得修改：业务代码、测试、配置和设计文档
- 独立交付：所有后续 AI 能从统一入口获得规则和命令

### 1. 背景

仓库已有 `CLAUDE.md`，但其他 AI 没有统一入口。重复维护完整规则会漂移，因此公共规则迁入 `AGENTS.md`，`CLAUDE.md` 只保留 Claude 适配。

### 2. 目标

创建可被所有开发 AI 使用的公共契约，并把十二段式任务包、停止条件、自检和交付格式固化到仓库。

### 3. 前置依赖

完整阅读批准设计第 16 节、根目录现有 `CLAUDE.md`、`docs/CONVENTIONS.md` 和本计划全局约束。

### 4. 输入与输出契约

- 输入：现有 `CLAUDE.md` 的强制门禁、命令和架构说明。
- 输出：根目录 `AGENTS.md`；更新后的 `CLAUDE.md` 第一条规则必须是“先完整阅读 `AGENTS.md`”。
- 规则优先级必须逐字包含批准设计第 16.1 节的顺序。

### 5. 修改范围

- 新建 `AGENTS.md`。
- 去除 `CLAUDE.md` 中与 `AGENTS.md` 重复的公共规则，保留 Claude 专属说明和指向公共契约的入口。

### 6. 禁止事项

- 不弱化 branch、diff、commit、push 审核门禁。
- 不把当前功能设计全文复制进 `AGENTS.md`。
- 不保留两套含义相同但措辞不同的公共交付规则。

### 7. 执行要求

- [ ] 提取现有门禁、命令、架构入口和文档规范。
- [ ] 写入批准设计第 16 节的停止条件、十二段结构、自检和固定交付格式。
- [ ] 在 `CLAUDE.md` 保留工具专属内容，并指向 `AGENTS.md`。

### 8. 实施步骤

- [ ] 创建 `AGENTS.md`，至少包含以下一级标题：

```markdown
# Claw_news Agent Development Contract
## 必读顺序
## 指令优先级
## 强制门禁
## 架构与稳定文档入口
## 常用检查命令
## 任务执行规则
## 强制停止条件
## 交付前自检
## 固定交付格式
```

- [ ] 修改 `CLAUDE.md` 开头，加入：

```markdown
## 必读入口

开始任何工作前必须完整阅读根目录 `AGENTS.md`。公共开发规则只以 `AGENTS.md` 为准；本文件仅补充 Claude 使用说明。
```

- [ ] 运行重复性检查并人工比较两份文件。

### 9. 验收标准

1. 任意 AI 只读 `AGENTS.md` 即可知道门禁、命令、停止条件和交付格式。
2. `CLAUDE.md` 明确先读 `AGENTS.md`，且没有与公共规则冲突。
3. 原有 diff 审核和 push 审核规则未丢失。

### 10. 检查命令

```bash
rg -n "AGENTS.md|强制停止|git diff|git push|交付前自检|固定交付格式" AGENTS.md CLAUDE.md
git diff --check
git diff -- AGENTS.md CLAUDE.md
```

预期：所有关键规则均命中；`git diff --check` 无输出。

### 11. 交付前自检

- [ ] 公共规则只有一个权威版本。
- [ ] 没有删除原有安全门禁。
- [ ] 没有写入机器绝对路径、密钥或本次临时状态。
- [ ] diff 只包含 `AGENTS.md` 和 `CLAUDE.md`。

### 12. 交付格式

按全局固定格式交付，并额外列出“从 `CLAUDE.md` 迁移到 `AGENTS.md` 的规则”和“仍保留在 `CLAUDE.md` 的专属内容”。交付后等待主审核 AI 批准再进入 Task 2。

---

## Task 2：来源策略配置与完整发布时间契约

**任务元数据**

- 依赖任务：Task 1
- 允许并行：完成后 Task 3、Task 4 可并行
- 预计创建：`app/content/__init__.py`、`app/content/source_policy.py`、`app/content/time_policy.py`、`tests/test_source_policy.py`、`tests/test_time_policy.py`
- 预计修改：`feeds.example.yaml`、`collectors/ai_rss.py`、`collectors/rss_sources.py`、`collectors/base.py`、`app/pipeline/candidate.py`、相关测试
- 不得修改：`aggregator/merger.py`、`app/pipeline/news_pipeline.py`、GitHub 链路

### 1. 背景

来源策略当前散落在硬编码权重和 feed 配置中，RSS 发布时间只保存日期，无法执行滚动小时有效期。

### 2. 目标

建立唯一 `SourcePolicy` registry 和小时级时间工具，让后续任务只消费稳定接口，不重复解析配置或时间。

### 3. 前置依赖

Task 1 已审核；阅读批准设计第 6、7、9 节。

### 4. 输入与输出契约

必须生产以下接口：

```python
@dataclass(frozen=True)
class SourcePolicy:
    source: str
    tier: Literal["fast_news", "vertical", "deep"]
    retention_hours: int
    quality_weight: float
    filter_profile: Literal["strict", "standard", "lenient"]

def build_source_policy_registry(feeds: list[dict]) -> dict[str, SourcePolicy]: ...
def resolve_source_policy(source: str, registry: dict[str, SourcePolicy]) -> SourcePolicy: ...
def candidate_effective_at(item: CandidateItem) -> tuple[datetime | None, str]: ...
def freshness_score(age_hours: float) -> float: ...
def is_today(value: datetime, now: datetime, tz_name: str) -> bool: ...
```

`CandidateItem.published_at` 保持字段名不变，但值允许完整 ISO 时间；新增 `published_time_source: str = ""`，允许值 `rss / fetched_at / legacy_date / unknown`。

### 5. 修改范围

- 策略字段随 feed dict 保留。
- 环境变量形式新增源没有策略时使用保守默认值。
- RSS `published_parsed` 转完整 ISO 时间；无发布时间时不伪造发布时间，由回退函数使用 `fetched_at`。

### 6. 禁止事项

- 不在 `aggregator/merger.py` 维护来源名单。
- 不将 `tier` 自动推断为来源质量。
- 不修改最终选材。
- 不让非法显式配置静默回退。

### 7. 执行要求

- [ ] 先为默认值、合法策略、非法 tier/时长/权重/profile 写失败测试。
- [ ] 先为 24/48/72 边界、时区今日判断和旧日期回退写失败测试。
- [ ] 再实现最小策略与时间模块。
- [ ] 更新所有默认 feed 和示例配置。

### 8. 实施步骤

- [ ] 在 `tests/test_source_policy.py` 写失败测试：

```python
def test_missing_policy_uses_conservative_default():
    registry = build_source_policy_registry([{
        "source": "new_source", "url": "https://x.test/feed", "category": "ai"
    }])
    assert registry["new_source"] == SourcePolicy(
        source="new_source", tier="vertical", retention_hours=48,
        quality_weight=3.0, filter_profile="standard",
    )

@pytest.mark.parametrize("field,value", [
    ("tier", "unknown"), ("retention_hours", 0),
    ("quality_weight", -1), ("filter_profile", "open"),
])
def test_explicit_invalid_policy_raises(field, value):
    feed = {"source": "bad", "url": "https://x.test", "category": "ai", field: value}
    with pytest.raises(ValueError, match="bad"):
        build_source_policy_registry([feed])
```

- [ ] 运行 `./venv/bin/pytest tests/test_source_policy.py -v`，预期因模块或接口不存在失败。
- [ ] 实现 `SourcePolicy`、常量 `DEFAULT_SOURCE_POLICY`、registry 和 resolver。
- [ ] 在 `tests/test_time_policy.py` 写边界测试：

```python
@pytest.mark.parametrize(("age", "score"), [(0, 3.0), (24, 3.0), (24.01, 1.5),
                                               (48, 1.5), (48.01, 0.5), (72, 0.5)])
def test_freshness_boundaries(age, score):
    assert freshness_score(age) == score

def test_effective_time_falls_back_to_fetched_at():
    item = CandidateItem(title="T", url="https://x", summary="S", source="x",
                         category="ai", published_at="", fetched_at="2026-07-10T08:00:00+08:00")
    value, reason = candidate_effective_at(item)
    assert value.isoformat() == "2026-07-10T08:00:00+08:00"
    assert reason == "fetched_at"
```

- [ ] 实现时间函数；对 naive datetime 按服务时区解释，禁止 naive/aware 直接相减。
- [ ] 修改 RSS 解析，使 `HotItem.pub_date` 接收完整 ISO 时间；保持旧测试中的 `yyyy-mm-dd` 可解析。
- [ ] 更新 `feeds.example.yaml` 为批准设计第 6.3 节的全部初始策略。
- [ ] 运行 Task 检查命令。

### 9. 验收标准

1. 所有默认源和自定义源都能解析为唯一策略。
2. 非法显式策略指出 source 和字段并失败。
3. 完整发布时间从 RSS 传到 `CandidateItem`。
4. 旧 `yyyy-mm-dd` 和空发布时间存在明确回退。
5. 时间分段和 `Asia/Shanghai` 今日边界被测试锁定。

### 10. 检查命令

```bash
./venv/bin/pytest tests/test_source_policy.py tests/test_time_policy.py tests/test_ai_rss.py tests/test_rss_collector.py tests/test_data_contracts.py -v
./venv/bin/ruff check app/content collectors/ai_rss.py collectors/rss_sources.py collectors/base.py app/pipeline/candidate.py tests/test_source_policy.py tests/test_time_policy.py
./venv/bin/ruff format --check app/content collectors/ai_rss.py collectors/rss_sources.py collectors/base.py app/pipeline/candidate.py tests/test_source_policy.py tests/test_time_policy.py
```

预期：全部 PASS；Ruff 无错误。

### 11. 交付前自检

- [ ] `quality_weight` 与 `tier` 没有混为一个字段。
- [ ] 所有默认源与设计表一致。
- [ ] 旧候选反序列化不因新增字段失败。
- [ ] 没有修改排序和发布行为。
- [ ] 示例配置为中文说明且无真实地址之外的敏感信息。

### 12. 交付格式

除全局格式外，附“最终 `SourcePolicy` 接口”“默认源策略表”“时间回退矩阵”和精确测试输出。

---

## Task 3：候选 7 天保留、72 小时读取与按源有效期过滤

**任务元数据**

- 依赖任务：Task 2
- 允许并行：Task 4
- 预计修改：`app/storage/ingestion_store.py`、`app/scheduler/jobs.py`、`tests/test_ingestion_store.py`、`tests/test_ingest_job.py`
- 不得修改：相关性规则、最终选材、评分常量、GitHub 链路

### 1. 背景

当前发布只读当天窗口，清理约保留 3 个自然日。跨日补位需要读取 72 小时，但物理存储需保留 7 天用于审计。

### 2. 目标

让 storage 提供最大 72 小时候选读取并保持已发布过滤；让 scheduler 只把物理清理期改为 7 天。来源有效期过滤使用 Task 2 的策略与时间接口。

### 3. 前置依赖

可导入 `SourcePolicy`、`resolve_source_policy()` 和 `candidate_effective_at()`。

### 4. 输入与输出契约

新增方法：

```python
def load_recent_candidates(
    self,
    window_end: str,
    lookback_hours: int = 72,
    pushed_urls: set[str] | None = None,
    pushed_keys: set[str] | None = None,
) -> list[CandidateItem]: ...

def filter_unexpired_candidates(
    items: list[CandidateItem],
    now: datetime,
    policies: dict[str, SourcePolicy],
) -> tuple[list[CandidateItem], list[dict]]: ...
```

第二个返回值是拒绝审计，至少包含 `canonical_key/source/reason/age_hours/retention_hours`。

### 5. 修改范围

- 保留现有 `load_window_candidates()` 兼容旧调用和测试。
- 新方法按 `fetched_at` 控制采集窗口；按 effective article time 控制来源有效期。
- `run_ingest_with_cleanup()` 改为 `keep_days=7`。

### 6. 禁止事项

- 不改变 `seen_keys` 含义或清空策略。
- 不把物理 7 天保留误用为推送有效期。
- 不在 storage 执行相关性或最终评分。

### 7. 执行要求

- [ ] 先覆盖跨四个自然日但仍在 72 小时内的边界。
- [ ] 覆盖 24 小时 fast_news、48 小时 vertical、72 小时 deep。
- [ ] 覆盖已发布过滤和无法得到时间的跨日拒绝。

### 8. 实施步骤

- [ ] 在 `tests/test_ingestion_store.py` 添加失败测试：

```python
def test_recent_loader_reads_72_hours_across_calendar_directories(tmp_path):
    store = IngestionStore(root_dir=tmp_path)
    window_end = "2026-07-11T09:00:00+08:00"
    _write_jsonl(tmp_path / "data/ingestion/2026-07-08", [
        _make_item(url="https://outside.test", fetched_at="2026-07-08T08:00:00+08:00"),
        _make_item(url="https://inside.test", fetched_at="2026-07-08T10:00:00+08:00"),
    ])
    result = store.load_recent_candidates(window_end=window_end, lookback_hours=72)
    assert {item.url for item in result} == {"https://inside.test"}

def test_source_retention_filters_independently():
    now = datetime.fromisoformat("2026-07-11T09:00:00+08:00")
    items = [
        _make_item(source="vertical_47h", published_at="2026-07-09T10:00:00+08:00"),
        _make_item(source="deep_71h", published_at="2026-07-08T10:00:00+08:00"),
        _make_item(source="fast_25h", published_at="2026-07-10T08:00:00+08:00"),
    ]
    policies = {
        "vertical_47h": SourcePolicy("vertical_47h", "vertical", 48, 3.0, "standard"),
        "deep_71h": SourcePolicy("deep_71h", "deep", 72, 4.0, "lenient"),
        "fast_25h": SourcePolicy("fast_25h", "fast_news", 24, 2.0, "strict"),
    }
    kept, rejected = filter_unexpired_candidates(items, now, policies)
    assert {item.source for item in kept} == {"vertical_47h", "deep_71h"}
    assert {row["reason"] for row in rejected} == {"expired"}
```

- [ ] 运行精确测试，预期接口不存在失败。
- [ ] 抽取 JSONL 目录遍历和折叠内部 helper，避免复制 `load_window_candidates()` 全部实现。
- [ ] 实现 `load_recent_candidates()` 和纯函数 `filter_unexpired_candidates()`。
- [ ] 修改 cleanup 为 7 天，并将 docstring 同步为 7 天。
- [ ] 运行 Task 检查命令。

### 9. 验收标准

1. 72 小时滚动窗口不会因自然日目录边界漏读。
2. 同一批候选按各自来源策略独立过期。
3. 已发布 URL/key 继续在 storage 层排除。
4. 旧 loader 行为不回归。
5. cleanup 只删除超过 7 天的原始候选目录。

### 10. 检查命令

```bash
./venv/bin/pytest tests/test_ingestion_store.py tests/test_ingest_job.py -v
./venv/bin/ruff check app/storage/ingestion_store.py app/scheduler/jobs.py tests/test_ingestion_store.py tests/test_ingest_job.py
./venv/bin/ruff format --check app/storage/ingestion_store.py app/scheduler/jobs.py tests/test_ingestion_store.py tests/test_ingest_job.py
```

### 11. 交付前自检

- [ ] 7 天物理保留和 72 小时读取是独立常量。
- [ ] 小时边界测试没有依赖真实当前时间。
- [ ] 旧记录读取异常只跳过坏行，不吞整个目录错误。
- [ ] diff 未触及相关性和选材模块。

### 12. 交付格式

附 24/48/72/168 小时边界测试表、兼容方法说明和被拒绝审计样例。

---

## Task 4：推送前跨分类相关性过滤

**任务元数据**

- 依赖任务：Task 2
- 允许并行：Task 3
- 预计创建：`app/classifiers/relevance_filter.py`、`tests/test_relevance_filter.py`
- 预计修改：`app/classifiers/__init__.py`、`feeds.example.yaml`
- 不得修改：storage、Merger、pipeline 编排、GitHub 链路

### 1. 背景

现有 `TopicClassifier` 是 AI 主题分类器，fallback 会让所有 AI 内容获得低置信度，且没有完整工具/游戏相关性模型。

### 2. 目标

提供纯规则、无网络、可解释的 `RelevanceFilter`，按分类和 source profile 判断文章能否参与本次推送。

### 3. 前置依赖

Task 2 的 `SourcePolicy.filter_profile` 已稳定；阅读设计第 8 节。

### 4. 输入与输出契约

```python
@dataclass(frozen=True)
class RelevanceResult:
    accepted: bool
    confidence: float
    reason: str
    matched_positive: tuple[str, ...] = ()
    matched_negative: tuple[str, ...] = ()

class RelevanceFilter:
    def evaluate(self, item: CandidateItem, policy: SourcePolicy) -> RelevanceResult: ...
    def evaluate_batch(self, items: list[CandidateItem], policies: dict[str, SourcePolicy]) \
            -> tuple[list[CandidateItem], list[dict]]: ...
```

`reason` 固定使用：`negative_rule`、`positive_rule`、`classifier_pass`、`below_threshold`、`rule_conflict`。

### 5. 修改范围

- AI、工具、游戏分别维护正向词和排除词。
- 复核置信度统一映射为 `0.9/0.7/0.5/0.3/0.1`。
- 若同时命中正负规则，返回 `rule_conflict` 且拒绝。

### 6. 禁止事项

- 不调用 LLM 或网络。
- 不改变 `TopicClassifier` 已有公开语义；可组合调用，但不能让其 AI fallback 直接代表其他分类相关。
- 不按来源名称无条件接受内容。
- 不在本 Task 接入生产 pipeline。

### 7. 执行要求

- [ ] 每类至少提供 5 个正例、5 个反例、3 个模糊例测试。
- [ ] IT之家汽车促销/运营商套餐/影视娱乐/家电降价必须作为 strict 反例。
- [ ] 深度源标题弱但摘要明确相关必须作为 lenient 正例。

### 8. 实施步骤

- [ ] 写失败测试：

```python
@pytest.mark.parametrize("title", ["汽车限时促销", "运营商套餐降价", "暑期电影票房"])
def test_strict_tool_source_rejects_known_noise(title):
    policy = SourcePolicy("ithome", "fast_news", 24, 2.0, "strict")
    result = RelevanceFilter().evaluate(
        CandidateItem(title=title, url="https://x.test", summary="普通资讯",
                      source="ithome", category="tool"), policy)
    assert result.accepted is False
    assert result.reason in {"negative_rule", "below_threshold"}

def test_negative_rule_wins_conflict():
    policy = SourcePolicy("ithome", "fast_news", 24, 2.0, "strict")
    item = CandidateItem(title="AI 手机汽车促销", url="https://x.test", summary="",
                         source="ithome", category="ai")
    result = RelevanceFilter().evaluate(item, policy)
    assert result.accepted is False
    assert result.reason == "rule_conflict"
    assert "ai" in result.matched_positive
    assert "汽车促销" in result.matched_negative

def test_lenient_deep_source_accepts_summary_evidence():
    policy = SourcePolicy("meituan_tech", "deep", 72, 4.0, "lenient")
    item = CandidateItem(title="一次实践复盘", url="https://x.test",
                         summary="分布式推理集群延迟优化",
                         source="meituan_tech", category="ai")
    result = RelevanceFilter().evaluate(item, policy)
    assert result.accepted is True
    assert result.confidence >= 0.3
```

- [ ] 运行 `./venv/bin/pytest tests/test_relevance_filter.py -v`，预期模块不存在失败。
- [ ] 实现归一化、正负匹配、冲突优先级、置信度和 batch 审计。
- [ ] 在示例配置中增加可覆盖的 `relevance_rules` 顶层结构；代码内只保留缺省规则。
- [ ] 运行 Task 检查命令。

### 9. 验收标准

1. 三类内容使用独立规则集。
2. 三档 profile 只改变复核阈值，不绕过排除规则。
3. 每次判断都有稳定 reason 和命中证据。
4. 组件无 I/O、无网络、给定输入输出确定。

### 10. 检查命令

```bash
./venv/bin/pytest tests/test_relevance_filter.py tests/test_topic_classifier.py -v
./venv/bin/ruff check app/classifiers/relevance_filter.py tests/test_relevance_filter.py
./venv/bin/ruff format --check app/classifiers/relevance_filter.py tests/test_relevance_filter.py
```

### 11. 交付前自检

- [ ] 反例没有通过 source 白名单绕过。
- [ ] 正负冲突始终拒绝。
- [ ] reason 枚举未出现临时字符串。
- [ ] 规则配置与示例同步。
- [ ] 没有接入 pipeline 或修改评分。

### 12. 交付格式

附三类测试样本表、profile 门槛矩阵、所有 reason 及其触发条件。

---

## Task 5：三阶段选材与唯一评分

**任务元数据**

- 依赖任务：Task 2、Task 3、Task 4
- 允许并行：无
- 预计创建：`app/pipeline/selection.py`、`tests/test_content_selection.py`
- 预计修改：`aggregator/merger.py`、`tests/test_merger.py`
- 不得修改：storage、collector、相关性规则、GitHub 链路

### 1. 背景

当前 Merger 只做每类 1 条保底和全量竞争，无法表达 AI 3/工具 2/游戏 2、跨日补位及跨阶段来源计数。

### 2. 目标

建立纯函数选材模块；Merger 保留兼容入口，但新 pipeline 使用显式 selection API。

### 3. 前置依赖

候选已完成未发布、有效期和相关性过滤；每篇候选能解析 effective time 和 SourcePolicy。

### 4. 输入与输出契约

```python
@dataclass(frozen=True)
class SelectionEvidence:
    canonical_key: str
    phase: Literal["today_guarantee", "historical_backfill", "today_competition"]
    final_score: float
    diversity_penalty: float
    selection_score: float

@dataclass(frozen=True)
class SelectionResult:
    selected: list[CandidateItem]
    evidence: list[SelectionEvidence]
    category_counts: dict[str, int]

def compute_final_score(item: CandidateItem, policy: SourcePolicy, now: datetime) -> float: ...
def select_digest(items: list[CandidateItem], policies: dict[str, SourcePolicy],
                  now: datetime, tz_name: str = "Asia/Shanghai",
                  top_n: int = 10) -> SelectionResult: ...
```

### 5. 修改范围

- 把当前单源 penalty helper 迁入或复用于 selection 模块。
- `aggregator.merger.compute_final_score()` 保持兼容，可委托新接口；旧 legacy path 不改。
- 分类顺序固定为 `ai`、`tool`、`game`，但每次选择都重新计算所有候选的 `selection_score`。

### 6. 禁止事项

- 不设置单源硬上限。
- 不让历史候选参加 phase 3。
- 不在阶段之间重置 source_counts。
- 不使用相关性置信度作为排名加分。

### 7. 执行要求

- [ ] 使用固定 now 和时区测试，不依赖 `datetime.now()`。
- [ ] 对每个阶段分别测试，并增加完整混合场景。
- [ ] 平分时固定按 `published_at` 新者、canonical key 字典序排序，保证确定性。

### 8. 实施步骤

- [ ] 写评分和 penalty 失败测试：

```python
def test_final_score_is_quality_plus_freshness():
    now = datetime.fromisoformat("2026-07-11T09:00:00+08:00")
    item = CandidateItem(title="T", url="https://x.test", summary="S", source="qbitai",
                         category="ai", published_at="2026-07-10T03:00:00+08:00")
    policy = SourcePolicy("qbitai", "vertical", 48, 3.5, "standard")
    assert compute_final_score(item, policy, now) == 5.0

@pytest.mark.parametrize(("count", "penalty"),
                         [(0, 0.0), (1, -1.0), (2, -2.0), (3, -3.5), (4, -5.0), (9, -5.0)])
def test_diversity_penalty(count, penalty):
    assert source_diversity_penalty(count) == penalty
```

- [ ] 写三阶段失败测试：

```python
def test_historical_items_only_fill_category_deficit():
    now = datetime.fromisoformat("2026-07-11T09:00:00+08:00")
    items, policies = build_selection_fixture(now)
    result = select_digest(items, policies, now)
    phases = {e.canonical_key: e.phase for e in result.evidence}
    assert phases["old-ai-1"] == "historical_backfill"
    assert "old-high-tool" not in {x.canonical_key for x in result.selected}

def test_source_counts_accumulate_across_phases():
    now = datetime.fromisoformat("2026-07-11T09:00:00+08:00")
    items, policies = build_cross_phase_same_source_fixture(now)
    result = select_digest(items, policies, now)
    penalties = [e.diversity_penalty for e in result.evidence if e.canonical_key.startswith("same-")]
    assert penalties == [0.0, -1.0, -2.0]
```

两个 fixture builder 必须在同一测试文件中显式创建完整 `CandidateItem` 列表：`build_selection_fixture()` 至少包含今日 AI 2、工具 2、游戏 2，历史 AI 1、历史高分工具 1；`build_cross_phase_same_source_fixture()` 必须让同一 source 分别在今日保底、历史补位和今日竞争三个阶段入选。不得依赖外部数据文件或真实当前时间。

- [ ] 运行测试，预期接口不存在失败。
- [ ] 实现稳定排序 helper、逐步 greedy pick、三个 phase 和 evidence。
- [ ] 修改 Merger 新评分路径委托或兼容新公式，确保 legacy 测试通过。
- [ ] 运行 Task 检查命令。

### 9. 验收标准

1. 今日充足时至少选出 3/2/2。
2. 今日不足时只从同分类历史候选补最低目标。
3. phase 3 只含今日候选。
4. 全程最多 10 条，无候选时允许少于 10。
5. source_counts 跨 phase 累计。
6. `final_score`、penalty、`selection_score` 都有证据。
7. 相同输入输出顺序稳定。

### 10. 检查命令

```bash
./venv/bin/pytest tests/test_content_selection.py tests/test_merger.py -v
./venv/bin/ruff check app/pipeline/selection.py aggregator/merger.py tests/test_content_selection.py tests/test_merger.py
./venv/bin/ruff format --check app/pipeline/selection.py aggregator/merger.py tests/test_content_selection.py tests/test_merger.py
```

### 11. 交付前自检

- [ ] 没有第二套 admission score。
- [ ] 没有把 tier 加进 final_score。
- [ ] 历史候选未进入自由竞争。
- [ ] penalty 映射和设计完全一致。
- [ ] legacy Merger 测试没有通过删除断言来“修复”。

### 12. 交付格式

附三阶段样例输入输出、每个入选项 evidence、兼容 Merger 的方式和全部精确测试结果。

---

## Task 6：接入统一发布链路与审计证据

**任务元数据**

- 依赖任务：Task 5
- 允许并行：无
- 预计修改：`app/pipeline/news_pipeline.py`、`app/tools/summary_result.py`、`app/storage/source_metrics_store.py`、`tests/test_news_pipeline.py`、`tests/test_main.py`、`tests/test_source_metrics_store.py`
- 不得修改：collector、规则常量、GitHub ranking、renderer 文案

### 1. 背景

前置任务只提供纯组件；本 Task 才改变生产发布读取和选材路径。

### 2. 目标

让 `run_pipeline()` 使用 72 小时读取、分源过期、相关性过滤和三阶段选材，并把拒绝、补位和评分证据写入 digest/metrics。

### 3. 前置依赖

Task 2 至 5 的接口和测试均已审核；不得在本 Task 修改其契约。

### 4. 输入与输出契约

`DigestPayload` 新增默认空字段：

```python
selection_evidence: list[dict] = field(default_factory=list)
relevance_rejections: list[dict] = field(default_factory=list)
```

每条 headline evidence 至少包括 `source/category/source_tier/final_score/diversity_penalty/selection_score/selection_phase/effective_at/time_source`。

`SourceMetricsStore` 新增独立发布指标接口，不再尝试把 `qbitai` 等文章来源计数写回 source=`rss` 的 ingest 行：

```python
def append_publish_source_metrics(
    self, published_at: str, rows: list[dict]
) -> Path: ...
```

每个 row 固定包含 `source/candidate_count/relevance_accepted_count/relevance_rejected_count/selected_today_count/selected_backfill_count/rejection_reasons`，写入 `data/source_metrics/YYYY-MM-DD/publish.jsonl`。保留现有 ingest `metrics.jsonl` 和兼容方法，不迁移历史文件。

### 5. 修改范围

- 使用 `config.tz` 判断今日。
- 相关性 rejected 不进入 LLM 输入。
- 历史读取失败降级到今日 loader，并把 publish 状态设为 `degraded`。
- publish metrics 按真实 item.source 聚合；ingest metrics 继续表达 collector=`rss` 的采集轮次，两者不得互相覆盖。

### 6. 禁止事项

- 不改变 push 成功、durable status 和部分写失败语义。
- 不把 GitHub 候选混入正文 selection。
- 不让回放代码进入生产 pipeline。
- 不吞历史读取或证据写入错误。

### 7. 执行要求

- [ ] 测试必须 mock 外部 LLM/WeCom，验证传给 LLM 的恰好是 selected。
- [ ] 覆盖历史读取失败降级、无合格候选 skipped、证据写失败 degraded。

### 8. 实施步骤

- [ ] 在 `tests/test_news_pipeline.py` 增加失败测试：

```python
async def test_pipeline_filters_then_selects_before_llm(monkeypatch):
    result = await run_pipeline(ctx, config)
    assert result.selected_count == 8
    assert [x["url"] for x in captured_llm_items] == EXPECTED_SELECTED_URLS
    assert "https://noise.test" not in captured_llm_items

async def test_historical_read_failure_degrades_to_today(monkeypatch):
    result = await run_pipeline(ctx, config)
    assert result.pushed is True
    assert result.status == "degraded"
    assert "historical_candidates_read_failed" in result.errors
```

- [ ] 运行精确测试，预期仍走旧当天 Merger 路径而失败。
- [ ] 在 pipeline 中按固定顺序串联：registry → recent load → expiry → relevance → select → LLM → push → evidence。
- [ ] 扩展 digest 和独立 `publish.jsonl` metrics 写入；保持默认字段和旧 ingest metrics 使旧调用兼容。
- [ ] 运行 Task 检查命令。

### 9. 验收标准

1. 生产 pipeline 不再直接把当天全部候选交给旧 Merger。
2. LLM 只收到最终 selected。
3. 历史读取失败时今日推送可继续且状态为 degraded。
4. 每个入选项和拒绝项有可回看证据。
5. 已有 durable publish 和 partial write 测试继续通过。
6. `qbitai`、`ithome` 等真实来源的 publish metrics 不再依赖查找 source=`rss` 的 ingest 行。

### 10. 检查命令

```bash
./venv/bin/pytest tests/test_news_pipeline.py tests/test_main.py tests/test_source_metrics_store.py tests/test_state_store_digest.py -v
./venv/bin/ruff check app/pipeline/news_pipeline.py app/tools/summary_result.py app/storage/source_metrics_store.py
./venv/bin/ruff format --check app/pipeline/news_pipeline.py app/tools/summary_result.py app/storage/source_metrics_store.py
```

### 11. 交付前自检

- [ ] 组件调用顺序与设计第 11 节一致。
- [ ] `pushed=True` 仍只代表真实主推送成功。
- [ ] 相关性过滤没有污染原始 JSONL。
- [ ] GitHub 路径 diff 仅允许上下文移动，不允许语义变化。
- [ ] 所有新增错误码有测试和 durable 证据。

### 12. 交付格式

附完整 pipeline 数据流、正常/降级/跳过三种结果样例、digest evidence 示例和测试结果。

---

## Task 7：只读历史回放、示例配置与运维说明

**任务元数据**

- 依赖任务：Task 6
- 允许并行：无
- 预计创建：`scripts/replay-content-selection.py`、`tests/test_content_replay.py`
- 预计修改：`feeds.example.yaml`、`docs/operations/daily-checklist.md`、`docs/operations/troubleshooting.md`、`docs/README.md`
- 不得修改：生产推送状态、GitHub 链路、评分常量

### 1. 背景

配置化规则需要可校准证据；直接手动触发生产推送风险过高。

### 2. 目标

提供只读回放命令，输出修改前后分布和过滤原因，并更新中文运维入口。

### 3. 前置依赖

Task 6 已能生成 selection/relevance evidence。

### 4. 输入与输出契约

命令：

```bash
python scripts/replay-content-selection.py --data-dir data --at 2026-07-11T09:00:00+08:00 --format json
```

JSON 至少输出 `candidate_count/eligible_count/selected_count/source_distribution/category_distribution/today_count/backfill_count/rejection_reasons/selected`。

### 5. 修改范围

- 脚本只调用纯读取、过滤和 selection 接口。
- 支持 `--format json` 和默认可读文本。
- 文档说明如何调整源策略和如何回放。

### 6. 禁止事项

- 不实例化 `WeComPusher`。
- 不写 `pushed_urls`、published keys、digest、metrics 或 publish status。
- 不接受 webhook 参数。
- 不把回放结果宣称为人工质量结论。

### 7. 执行要求

- [ ] 先写“所有生产状态文件 hash 不变”的测试。
- [ ] 输出必须确定性排序，便于版本对比。
- [ ] 非法时间、缺目录和坏配置明确失败。

### 8. 实施步骤

- [ ] 写失败测试：

```python
def test_replay_is_read_only(tmp_path):
    before = snapshot_hashes(tmp_path)
    result = run_replay(data_dir=tmp_path, at="2026-07-11T09:00:00+08:00")
    assert result["selected_count"] >= 0
    assert snapshot_hashes(tmp_path) == before

def test_replay_reports_backfill_and_rejections(tmp_path):
    fixture_dir = seed_replay_fixture(tmp_path)
    result = run_replay(data_dir=fixture_dir, at="2026-07-11T09:00:00+08:00")
    assert result["backfill_count"] == 2
    assert result["rejection_reasons"]["negative_rule"] == 3
```

`snapshot_hashes()` 必须递归计算 fixture 目录现有文件的 SHA-256；`seed_replay_fixture()` 必须只在调用 `run_replay()` 前创建候选、配置和状态样本，确保 hash 对比覆盖脚本可能触及的全部文件。

- [ ] 运行精确测试，预期模块不存在失败。
- [ ] 实现可导入 `run_replay()` 和薄 CLI main。
- [ ] 更新中文 daily checklist 和 troubleshooting，加入回放命令、结果解释和禁止推送说明。
- [ ] 运行 Task 检查命令。

### 9. 验收标准

1. 同一数据和 at 时间产生稳定结果。
2. 脚本运行前后生产状态文件不变。
3. 输出足以比较来源、分类、跨日补位和拒绝原因。
4. 运维人员可从 docs index 找到命令。

### 10. 检查命令

```bash
./venv/bin/pytest tests/test_content_replay.py -v
./venv/bin/ruff check scripts/replay-content-selection.py tests/test_content_replay.py
./venv/bin/ruff format --check scripts/replay-content-selection.py tests/test_content_replay.py
python scripts/replay-content-selection.py --help
```

### 11. 交付前自检

- [ ] 脚本没有任何写路径。
- [ ] 测试显式验证状态文件未变化。
- [ ] 文档未包含真实 webhook、密钥或机器路径。
- [ ] 示例配置与 Task 2 最终字段一致。

### 12. 交付格式

附一份脱敏 JSON 输出、一份可读文本输出、只读证明和文档入口链接。

---

## Task 8：全链路回归、历史样本验收与最终报告

**任务元数据**

- 依赖任务：Task 1 至 Task 7
- 允许并行：可把代码审查和历史回放交给不同审核 AI，但不得同时修改代码
- 预计修改：仅测试修正、任务直接相关缺陷和 `docs/operations/content-selection-acceptance.md`
- 不得修改：已批准常量、范围外重构、GitHub 链路、新功能

### 1. 背景

单元测试通过不能证明真实混合候选结构改善。本 Task 只做回归、回放和契约验收，不扩展功能。

### 2. 目标

用完整测试和至少一份历史候选样本证明来源分布改善、分类补位正确、无关项下降且主链路稳定。

### 3. 前置依赖

所有 Task 独立审核通过；工作区无未归属改动；测试数据已脱敏。

### 4. 输入与输出契约

最终验收报告固定包含：版本/commit、样本时间窗、配置快照摘要、修改前后分布、十二条设计验收标准证据、失败项、残留风险和结论。结论只允许 `passed / passed_with_notes / failed`。

### 5. 修改范围

- 允许修复本功能直接导致的测试或语义缺陷。
- 每个修复必须先增加复现测试并单独审核。
- 新想法写入报告后续项，不实现。

### 6. 禁止事项

- 不为了让测试绿而删除断言、放宽门槛或修改样本。
- 不真实推送。
- 不把单次回放当成自动分级依据。
- 不顺手重构大文件。

### 7. 执行要求

- [ ] 先运行精确功能测试，再运行全量 test/lint/format。
- [ ] 回放至少覆盖“IT之家占多数”“AI 当天不足”“深度源跨 72 小时边界”三个场景。
- [ ] 使用另一审核 AI 做 spec compliance review，再做 code quality review。

### 8. 实施步骤

- [ ] 运行功能测试集合：

```bash
./venv/bin/pytest tests/test_source_policy.py tests/test_time_policy.py \
  tests/test_ingestion_store.py tests/test_relevance_filter.py \
  tests/test_content_selection.py tests/test_news_pipeline.py \
  tests/test_content_replay.py -v
```

- [ ] 运行完整验证：

```bash
make test
make lint
./venv/bin/ruff format --check .
```

- [ ] 对固定历史样本运行回放，并保存脱敏输出到验收报告，不保存生产数据副本。
- [ ] 逐条核对设计第 14 节 12 项验收标准；每项填写证据命令、输出摘要和结论。
- [ ] 执行 spec compliance review：只检查实现是否忠实覆盖设计，不提范围外优化。
- [ ] 执行 code quality review：检查边界、错误语义、可维护性和测试可信度。
- [ ] 若发现缺陷，退回对应 Task 修复并重新执行受影响检查与完整验证。

### 9. 验收标准

1. 设计第 14 节十二项均有证据。
2. 全量 pytest、Ruff lint、Ruff format 全部通过。
3. 回放不修改任何生产状态。
4. 高频源数量优势不再直接转化为最终多数。
5. 跨日内容只出现在 `historical_backfill`。
6. 无未解释失败、未验证声明或范围外改动。

### 10. 检查命令

```bash
git status --short
git diff --check
make test
make lint
./venv/bin/ruff format --check .
python scripts/replay-content-selection.py --data-dir data --at 2026-07-11T09:00:00+08:00 --format json
```

预期：工作区改动均有归属；diff check、测试、lint、format 通过；回放退出码 0。

### 11. 交付前自检

- [ ] 验收报告没有生产候选原文、密钥、webhook 或机器绝对路径。
- [ ] 每条“通过”都对应本轮实际命令输出。
- [ ] 未运行的检查明确写“未验证”。
- [ ] `passed_with_notes` 的 notes 都是本范围直接残留风险。
- [ ] 没有将未来自动分级描述为已实现。

### 12. 交付格式

按全局格式交付，并附：

1. 最终结论；
2. 精确 commit；
3. 全量命令与通过数量；
4. 修改前后分布表；
5. 十二项验收证据表；
6. 两轮审核结论；
7. 残留风险与后续项。

---

## 主调度 AI 的执行规则

1. 每个 Task 使用全新开发 AI，不复用上一个 Task 的隐含上下文。
2. 派发时只提供 `AGENTS.md`、本计划当前 Task、批准设计的相关章节和前置接口交付，不发送无边界的整段聊天记录。
3. 每个 Task 完成后先做 spec compliance review，再做 code quality review；任何一轮不通过都退回原开发 AI 修正。
4. 主调度 AI 在开始下一个依赖 Task 前，必须核对前置 Task 的接口名称、类型和 commit。
5. 并行任务只能修改互不重叠文件；Task 3 与 Task 4 是唯一默认并行组。
6. 开发 AI 不得自行 commit，除非任务派发信息明确授权且 diff 已由用户或主调度 AI 按仓库门禁审核。
7. 任何 push、PR、部署或真实推送必须单独获得用户明确授权。

## 计划自检映射

| 设计要求 | 实施 Task |
|---|---|
| 多 AI 契约 | Task 1 |
| 人工来源策略与质量权重 | Task 2 |
| 小时级发布时间与 freshness | Task 2 |
| 7 天存储与 72 小时读取 | Task 3 |
| 24/48/72 分源有效期 | Task 3 |
| 跨分类相关性与解释 | Task 4 |
| 唯一 final_score | Task 5 |
| 3/2/2、跨日补位、今日竞争 | Task 5 |
| 跨阶段单源惩罚 | Task 5 |
| pipeline 接入与 durable evidence | Task 6 |
| 指标与未来建议数据 | Task 6、Task 7 |
| 只读回放 | Task 7 |
| 全链路验收 | Task 8 |

本计划不包含自动源分级、LLM 相关性判断、GitHub 排序修改或真实部署。
