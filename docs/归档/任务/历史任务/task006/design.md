# 统一 AI 日报发布流程合并设计文档

## 1. 本轮目标

本轮目标不是继续并行维护“旧 CLI 热点链路”和“新服务摘要链路”，而是收敛为一条统一发布流程。

要达成的结果是：

1. 对外不再区分新旧体系，只保留一个正式发布流程
2. 正式运行入口统一为服务化入口
3. 微信端统一输出一条 WeCom markdown 日报
4. 复用旧体系的成熟能力：采集、选材、状态持久化、markdown 推送
5. 在不引入数据库和大规模来源扩展的前提下，完成一次轻量评分升级
6. 增加轻量文件型候选池，支持高频抓取与定时发布解耦

---

## 2. 设计结论

### 2.1 总体方案

采用“服务入口统一、旧能力内聚复用”的方案：

1. 保留 `FastAPI + APScheduler` 作为唯一正式入口
2. 不再让 `main.py` 作为正式发布主链路
3. 将旧体系成熟能力吸收到统一 pipeline 内：
   - `collectors/*`
   - `aggregator/merger.py`
   - `infra/storage/state_store.py`
   - `pusher/wecom.py`
4. 统一输出为一条 WeCom markdown 消息，标题以超链接形式展示

### 2.2 为什么不继续双轨并行

继续双轨并行的直接代价是：

1. 来源扩展要改两遍
2. 推送样式要维护两套
3. 评分逻辑会逐步漂移
4. 部署和验证会长期保留两种心智
5. review 难以判断哪条链路才是正式交付物

因此本轮必须明确：

1. 对外只保留一条正式链路
2. 旧链路能力只作为内部模块存在
3. CLI 可以短期保留为兼容壳，但不再作为产品主入口

### 2.3 为什么本轮不上数据库

数据库是合理方向，但不应和本轮统一发布流程绑在一起。

本轮如果同时引入数据库，会导致：

1. 数据模型、部署、状态、选材一起变更
2. 范围膨胀到“内容系统重构”
3. 无法快速验证统一流程本身是否成立

因此本轮结论是：

1. 本轮不引入 PostgreSQL
2. 本轮保留文件状态持久化
3. 本轮抓取态数据使用文件型候选池
4. 后续如果升级数据库，应在统一发布流程稳定后独立推进

---

## 3. 设计边界

### 3.1 本轮纳入范围

1. 统一正式服务入口
2. 统一微信端推送样式为 markdown
3. 统一采集、选材、摘要、推送、状态落盘链路
4. 新增轻量文件型候选池，承接高频抓取结果
5. 轻量评分增强：
   - 来源分层
   - 主题桶
   - 规则轻分类
   - 关键词降级为辅助项
6. 统一部署和验证流程

### 3.2 本轮明确不做

1. PostgreSQL 或其他数据库
2. 网页详情页 / 历史列表
3. GitHub 热点正式接入
4. 大规模新来源扩展
5. LLM 专门分类子流程
6. 多条微信消息拆分策略
7. 多副本调度或复杂分布式锁

---

## 4. 统一后的模块设计

### 4.1 Service Layer

保留：

1. `app/main.py`
2. `app/scheduler/jobs.py`

职责：

1. 暴露 `/health` 与 `/run/news`
2. 承载服务生命周期
3. 注册定时调度
4. 调用统一 pipeline

原则：

1. Service Layer 只做入口，不承载业务决策

### 4.2 Unified Pipeline Layer

建议新增：

1. `app/pipeline/news_pipeline.py`

职责：

1. 串联发布主流程：
   - 采集
   - 轻分类
   - 评分
   - 选材
   - 摘要
   - 渲染
   - 推送
   - 状态落盘
2. 成为唯一正式业务内核

原则：

1. HTTP 触发和定时触发都调用同一个 pipeline
2. CLI 若保留兼容，也只能调用这个 pipeline

### 4.2.1 统一运行上下文

统一 pipeline 不得直接读取入口侧的隐式语义，必须显式接收一份运行上下文。

建议结构：

```text
RunContext
- trigger_mode
- period
- time_window
- publish_scope
- state_namespace
```

设计结论：

1. 所有触发入口都必须先构造 `RunContext`
2. pipeline 只能通过 `RunContext` 获取 period、窗口和状态语义
3. 不允许 HTTP、scheduler、CLI 兼容入口各自分叉逻辑
4. 本轮默认 `period` 固定为 `morning`
5. 本轮 `time_window` 固定为当前发布日 `00:00:00` 到触发时刻
6. 本轮 `publish_scope` 固定为 `ai_only`
7. 本轮 `state_namespace` 固定为 `ai_digest`

### 4.3 Collection Layer

复用旧体系：

1. `collectors/rss_sources.py`
2. `collectors/huggingface.py`
3. `collectors/taptap.py`
4. 旧链路中的 `collect_all()` 设计思路

职责：

1. 提供统一候选 item 列表
2. 屏蔽不同来源的抓取差异
3. 保持来源级容错
4. 为高频抓取任务提供标准化原始候选输入

本轮结论：

1. 不再以 `app/tools/crawler.py` 作为长期唯一采集主逻辑
2. 统一候选输入应来自旧体系已验证过的 collector 组合
3. 旧 `game/device` 模块可仅作为内部兼容采集能力保留，但不得进入本轮正式外发 digest

### 4.3.1 Ingestion Store Layer

建议新增：

1. `app/storage/ingestion_store.py`

职责：

1. 接收高频抓取任务输出的 `CandidateItem`
2. 按 `canonical_key` / `url` 做本地去重合并
3. 将候选项落盘到文件型候选池
4. 为正式发布任务提供窗口内候选项读取
5. 执行过期清理

本轮存储形态固定为：

1. `data/ingestion/YYYY-MM-DD/candidates.jsonl`
2. `data/ingestion/YYYY-MM-DD/index.json`

其中：

1. `candidates.jsonl` 按行保存标准化后的 `CandidateItem`
2. `index.json` 保存轻量索引和抓取态元数据，例如：
   - `date`
   - `seen_keys`
   - `source_failures`
   - `item_count`
   - `updated_at`

本轮设计要求：

1. 高频抓取任务只负责“采集 + 标准化 + 入池”，不做 LLM 摘要
2. 正式发布任务只从 `Ingestion Store` 读取候选，不直接重建一条正式全量抓取主链路
3. 候选池至少保留最近 `3` 个发布日
4. 候选池与正式 digest 落盘必须分离
5. `Ingestion Store` 的逻辑聚合视图包含 `items + seen_keys + source_failures + item_count + updated_at`
6. 该聚合视图不要求作为单个物理文件存在
7. `append_or_merge` 的实现口径固定为：
   - 写入时允许向 `candidates.jsonl` 追加同 `canonical_key` 的多条原始记录
   - 读池时必须按 `canonical_key` 逻辑折叠
   - 冲突优先级依次为：`published_at` 更新、`fetched_at` 更新、`summary` 更完整

### 4.3.2 统一 Candidate Item 契约

Collector 输出不得直接把不同历史模型混进 pipeline，必须先适配成统一候选项结构。

最小字段集：

```text
CandidateItem
- title
- url
- summary
- source
- category
- published_at
- fetched_at
- canonical_key
- ingest_run_id
- topic（发布阶段补充，可为空）
- topic_confidence（发布阶段补充，可为空）
- source_weight（发布阶段补充，可为空）
- topic_weight（发布阶段补充，可为空）
- keyword_bonus（发布阶段补充，可为空）
- final_score（发布阶段补充，可为空）
```

设计结论：

1. 旧 `HotItem` 进入统一 pipeline 前，必须先转换为 `CandidateItem`
2. 后续 classifier、scoring、renderer、state 只能依赖统一契约，不得各自消费不同历史字段
3. 高频入池阶段只要求基础抓取字段非空，分类和评分字段允许为空

### 4.4 Classification Layer

建议新增：

1. `app/classifiers/topic_classifier.py`

职责：

1. 根据来源、标题、摘要，对候选内容做规则轻分类
2. 产出主题桶结果

建议主题桶：

1. `model_release`
2. `agent_workflow`
3. `developer_tooling`
4. `research_benchmark`
5. `infrastructure`
6. `application_case`

本轮结论：

1. 先使用规则分类
2. 不依赖额外 LLM 分类步骤

### 4.5 Scoring Layer

基于：

1. `aggregator/merger.py`

进行增强。

本轮目标不是彻底重写评分，而是在旧评分框架上升级主信号。

新评分结构建议：

```text
final_score =
  source_weight
  + topic_weight
  + keyword_bonus
  + time_modifier
```

其中：

1. `source_weight`
   - 本轮固定映射：
     - `huggingface = 4.0`
     - `qbitai = 3.0`
     - 其他进入本轮 `ai_only` 发布范围的 RSS AI 垂类来源 = `3.0`
2. `topic_weight`
   - 本轮固定映射：
     - `model_release = 3.0`
     - `agent_workflow = 2.5`
     - `developer_tooling = 2.0`
     - `research_benchmark = 2.0`
     - `infrastructure = 1.5`
     - `application_case = 1.0`
3. `keyword_bonus`
   - 仅作为辅助项，命中时固定加 `0.5`
4. `time_modifier`
   - 固定复用 `collectors.base.time_modifier(pub_date, "morning")`

原则：

1. 关键词命中不再是主评分信号
2. 主题与来源成为主信号
3. `topic_confidence` 本轮不直接参与 `final_score`
4. `keyword_bonus` 本轮固定为布尔加分项

### 4.6 Selection Layer

仍复用：

1. `Merger`

职责：

1. 去重
2. 保底选材
3. 全量竞争补位
4. 输出最终候选

本轮设计要求：

1. `Merger` 输入项需包含轻分类和新评分结果
2. 选材逻辑不再只依赖 RSS 排位 + 关键词
3. 旧 `Merger` 的“每源至少 1 条”保底规则本轮不保留

### 4.7 Summary Layer

保留：

1. `app/tools/llm.py`

职责：

1. 对最终候选项生成摘要结果

本轮结论：

1. 仍允许使用 LLM 生成摘要
2. 但最终推送格式不应由 LLM 直接控制
3. 渲染格式必须由程序端统一控制

### 4.7.1 Summary Result 契约

LLM 层输出必须冻结为结构化摘要结果。

最小字段集：

```text
SummaryItem
- title
- url
- core_summary
- importance
- trend
```

统一输出结构固定为：

```text
SummaryResult
- headline_items: list[SummaryItem]
- daily_judgement: str
```

设计结论：

1. LLM 不得直接输出最终 markdown
2. renderer 只能消费 `SummaryResult`
3. 若需要兼容当前 `summary_preview`，应从 `SummaryResult` 派生，而不是从自由文本截断

### 4.8 Render Layer

建议新增：

1. `app/renderers/wecom_markdown.py`

职责：

1. 将选材 + 摘要结果渲染为统一 markdown 模板

本轮样式原则：

1. 一条消息
2. 标题超链接
3. 不展示裸长链接
4. 结构固定、简单、适配企微 markdown 子集

### 4.8.1 旧推送模块适配层

旧 `pusher/wecom.py` 当前是“分类循环发送多条消息”的模型，不可直接视为与本轮目标等价。

本轮必须显式新增一个适配层，职责是：

1. 接收 `SummaryResult`
2. 渲染成单条 markdown digest
3. 调用单消息推送接口

设计结论：

1. 不能直接复用旧 `push()` 的“逐 category 多消息发送”语义
2. 必须定义单消息 publish API
3. 若复用旧模块，也只能复用其 markdown payload 能力，而非多消息流程语义

### 4.9 Publish Layer

复用旧体系：

1. `pusher/wecom.py`

职责：

1. 执行 WeCom markdown 推送
2. 保留标题超链接能力

本轮结论：

1. 正式推送统一收敛到 markdown
2. 新服务不再继续以 `text` 作为主发布形态

### 4.10 State Layer

复用旧体系：

1. `infra/storage/state_store.py`

职责：

1. 维护 `pushed_urls`
2. 写入日报 JSON
3. 保留部分成功状态

本轮结论：

1. 状态落盘统一依赖 `StateStore`
2. 不再只靠进程内结果与日志判断成功状态

### 4.10.1 状态模型适配层

旧 `StateStore` 当前更接近 category-shaped JSON。

本轮统一冻结为 `digest-shaped JSON`，最小结构为：

```text
DigestPayload
- date
- period
- published_at
- trigger_mode
- headline_items
- daily_judgement
- source_failures
- published_urls
- published_keys
```

设计结论：

1. 正式 digest 持久化结构固定为 digest-shaped JSON
2. push 成功但 state 写失败的语义必须明确
3. 部分来源失败但日报成功发布的语义必须明确
4. 为支持发布读池过滤，digest 必须保存 `published_urls` 与 `published_keys`

---

## 5. 数据走向

统一后的主数据流为：

```text
High-Frequency Ingest Scheduler
  -> Collectors gather raw items
  -> Candidate normalization
  -> Ingestion Store append_or_merge

Publish Trigger (Scheduler / HTTP / CLI compat)
  -> Unified Pipeline
  -> Ingestion Store load_window_candidates
  -> Topic Classifier assigns topic bucket
  -> Scoring computes item scores
  -> Merger selects final candidates
  -> LLM summarizes selected items
  -> Markdown Renderer builds final message
  -> WeCom Markdown Push
  -> StateStore persists publish state
```

### 5.1 高频抓取入池

来源：

1. 高频 ingest scheduler

流程：

1. 定时运行 collector
2. 标准化为 `CandidateItem`
3. 写入 `Ingestion Store`
4. 记录来源失败与索引元数据

要求：

1. 单个来源失败不应中断整轮 ingest
2. ingest 不得触发 LLM 摘要
3. ingest 与 publish 要共享 `CandidateItem` 契约

### 5.2 正式发布触发

来源：

1. APScheduler
2. `POST /run/news`

二者都进入同一 publish pipeline。

### 5.3 读池与窗口装载

发布前先执行：

1. 从 `Ingestion Store` 读取当前 `time_window` 内候选项
2. 过滤已发布 URL / key
3. 输出待分类候选集

要求：

1. 发布读池必须同时执行窗口过滤和已发布过滤
2. 发布链路不得在这一阶段重新调用正式全量抓取逻辑

### 5.4 轻分类

对每个 item 输出：

1. `topic`
2. `topic_confidence` 或等价规则结果

### 5.5 评分

根据：

1. 来源层级
2. 主题桶
3. 关键词辅助
4. 时间修正

输出排序分。

### 5.6 选材

`Merger` 对候选项进行：

1. 去重
2. 竞争排序
3. 最终候选输出

### 5.7 摘要

LLM 只处理最终候选，不处理全量原始候选。

### 5.8 渲染

程序端负责最终 markdown 结构，避免 LLM 直接决定消息版式。

### 5.9 推送与状态

成功推送后：

1. 更新 `pushed_urls`
2. 写入日报 JSON
3. 保留本轮运行结果

失败顺序语义必须冻结：

1. push 成功、state 写失败如何上报
2. collect 部分失败、publish 成功如何记录
3. 单条消息发布成功后，state 应写入哪种 digest 结构

---

## 6. 推送样式设计

本轮统一输出为一条 WeCom markdown 消息。

推荐样式：

```markdown
# 今日 AI 新闻摘要

**1. [标题](链接)**
> 核心内容：……
>
> 重要性：高
>
> 趋势判断：……

**2. [标题](链接)**
> 核心内容：……
>
> 重要性：中
>
> 趋势判断：……

> 今日一句话判断：……
```

样式约束：

1. 标题必须可点击
2. 不展示裸长链接
3. 不使用复杂嵌套列表
4. 不依赖复杂 markdown 子集能力

---

## 7. 部署与运维方案

### 7.1 正式环境

统一使用：

1. `.env`
2. `docker-compose.yml`

标准流程：

```bash
git pull
docker compose up -d --build
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/run/news
```

### 7.2 验证环境

统一使用：

1. `.env.verify`
2. `docker-compose.verify.yml`

标准流程：

```bash
docker compose down
docker compose --env-file .env.verify -f docker-compose.yml -f docker-compose.verify.yml up -d --build
curl -X POST http://127.0.0.1:8000/run/news
```

### 7.3 设计结论

部署心智必须统一成：

1. 一个正式服务
2. 一套正式环境变量
3. 一套验证覆盖环境

不再同时保留“双链路部署”的正式口径。

---

## 8. 风险与迁移策略

### 8.1 主要风险

1. 旧能力接入后，模块边界可能短期不够整洁
2. markdown 推送切换后，需要重新验证微信端观感
3. 评分轻改造可能需要 1 到 2 轮权重调参

### 8.2 迁移策略

本轮建议：

1. 先统一正式主链路
2. CLI 保留兼容壳，不再作为正式主流程
3. review 以后只围绕统一服务链路进行

---

## 9. 结论

本轮的本质不是“继续加功能”，而是把项目从两套演进中的链路收敛成一套正式发布系统。

做完之后，项目应达到：

1. 入口统一
2. 推送统一
3. 状态统一
4. 部署统一
5. 评分信号更稳
6. 后续数据库化、网页端、来源扩展都能沿着统一链路继续演进
