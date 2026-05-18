# 统一 AI 日报发布流程合并实施文档

> **给执行开发的 agent：** 本计划用于指导统一发布流程改造。执行时以“先统一正式链路，再做评分增强”为顺序，不允许顺手引入数据库、网页端或大规模来源扩展。

**目标：** 合并新旧发布流程，统一服务入口、选材与推送链路，并在本轮完成主题桶、规则轻分类和关键词降级。

**架构：** `High-Frequency Ingest Scheduler -> Collectors -> Ingestion Store -> Publish Pipeline -> Topic Classifier -> Merger -> LLM -> Markdown Renderer -> WeCom Markdown Push -> StateStore`

**技术栈：** FastAPI、APScheduler、现有 collectors、现有 Merger、现有 StateStore、现有 WeCom markdown 推送

---

## 文件结构

**新增建议：**

- `app/pipeline/news_pipeline.py`
- `app/classifiers/topic_classifier.py`
- `app/renderers/wecom_markdown.py`
- `app/storage/ingestion_store.py`
- `tests/test_topic_classifier.py`
- `tests/test_wecom_markdown_renderer.py`
- `tests/test_ingestion_store.py`

**重点修改：**

- `app/main.py`
- `app/agents/news_agent.py`
- `app/scheduler/jobs.py`
- `app/tools/llm.py`
- `aggregator/merger.py`
- `infra/storage/state_store.py`（若需最小适配）
- `docker-compose.yml`
- `README.md`
- `docs/operations/deploy/server-guide.md`

**可复用现有模块：**

- `collectors/rss_sources.py`
- `collectors/huggingface.py`
- `collectors/taptap.py`
- `pusher/wecom.py`
- `infra/storage/state_store.py`

---

## 任务 0：冻结接口与适配契约

**文件：**

- `spec/task006/contract.md`
- `docs/tasks/task006/design.md`
- `docs/tasks/task006/plan.md`

- [ ] **步骤 1：冻结统一运行上下文**

要求：

1. 必须定义 `RunContext`
2. 至少包含：
   - `trigger_mode`
   - `period`
   - `time_window`
   - `publish_scope`
   - `state_namespace`
3. 本轮固定：
   - `period=morning`
   - `time_window=当前发布日 00:00:00 到触发时刻`
   - `publish_scope=ai_only`
   - `state_namespace=ai_digest`

- [ ] **步骤 2：冻结统一数据结构**

要求：

1. 必须定义 `CandidateItem`
2. 必须定义 `SummaryResult`
3. 必须定义 `PublishResult`
4. 必须定义 `Digest Persistence Payload`
5. 必须定义 `Ingestion Persistence Payload`
6. `SummaryResult` 顶层固定为：
   - `headline_items`
   - `daily_judgement`
7. `Digest Persistence Payload` 固定为 digest-shaped JSON
8. `CandidateItem` 必须补充：
   - `fetched_at`
   - `canonical_key`
   - `ingest_run_id`
9. `Ingestion Persistence Payload` 必须固定为文件型候选池对应的逻辑聚合结构
10. 必须明确哪些 `CandidateItem` 字段是入池必填，哪些字段允许在发布前为空

- [ ] **步骤 3：冻结旧模块适配层**

要求：

1. 必须明确旧 `Merger` 如何适配单条 AI digest
2. 必须明确旧 `WeComPusher` 如何适配单消息 publish API
3. 必须明确旧 `StateStore` 适配为 digest-shaped JSON
4. 必须明确 `Ingestion Store` 与 `StateStore` 的职责边界

---

## 任务 1：统一正式主链路

**文件：**

- `app/main.py`
- `app/agents/news_agent.py`
- 新增：`app/pipeline/news_pipeline.py`

- [ ] **步骤 1：抽出统一 pipeline**

要求：

1. 统一正式业务主链路必须位于一个明确的 pipeline 模块
2. HTTP 触发与 scheduler 触发都调用这条 pipeline
3. CLI 若保留兼容，只允许复用这条 pipeline

- [ ] **步骤 2：收敛 `NewsAgent` 角色**

要求：

1. `NewsAgent` 不再内嵌临时版业务流程
2. 只负责调用统一 pipeline，并包装并发/锁语义

- [ ] **步骤 3：确认正式入口唯一性**

要求：

1. `app/main.py` 是唯一正式服务入口
2. 不再让 `main.py` 继续演进为第二套业务主逻辑

---

## 任务 2：引入轻量候选池

**文件：**

- 新增：`app/storage/ingestion_store.py`
- `app/pipeline/news_pipeline.py`
- `tests/test_ingestion_store.py`

- [ ] **步骤 1：落定文件型候选池路径**

要求：

1. 候选池必须使用文件型持久化
2. 最小路径固定为：
   - `data/ingestion/YYYY-MM-DD/candidates.jsonl`
   - `data/ingestion/YYYY-MM-DD/index.json`
3. 候选池与 digest JSON 不得混存
4. `candidates.jsonl` 只存 `CandidateItem` 记录
5. `index.json` 至少存：
   - `date`
   - `seen_keys`
   - `source_failures`
   - `item_count`
   - `updated_at`

- [ ] **步骤 2：实现入池语义**

要求：

1. 高频抓取任务负责把标准化后的 `CandidateItem` 写入候选池
2. 必须支持按 `canonical_key` / `url` 去重合并
3. 必须记录：
   - `seen_keys`
   - `source_failures`
   - `item_count`
   - `updated_at`
4. `append_or_merge` 必须固定为：
   - 写入时允许对同一 `canonical_key` 追加多条原始记录
   - 读池时按 `canonical_key` 逻辑折叠
   - 折叠优先级：`published_at` 更新优先，其次 `fetched_at` 更新，再次 `summary` 更完整

- [ ] **步骤 3：实现读池语义**

要求：

1. 正式发布任务必须从候选池读取窗口内候选
2. 读取逻辑必须支持：
   - `time_window` 过滤
   - 已发布项过滤
3. 不允许正式发布阶段重新构造 RSS-only 全量抓取主链路
4. 发布读池必须同时执行 `time_window` 过滤和已发布 `URL / key` 过滤

- [ ] **步骤 3.5：接入高频 ingest scheduler**

**文件：**

- `app/scheduler/jobs.py`
- `app/main.py`

要求：

1. 必须新增独立的 ingest job
2. ingest job 负责定时执行：
   - collector 采集
   - 标准化
   - `Ingestion Store.append_or_merge`
3. publish job 与 ingest job 不得混成同一职责
4. 计划中必须明确：先执行高频入池，再执行定时发布

- [ ] **步骤 4：实现过期清理**

要求：

1. 候选池至少保留最近 `3` 个发布日
2. 过期清理职责归 `Ingestion Store`
3. 过期清理由 ingest job 或独立清理步骤触发，不得混入发布流程

---

## 任务 3：统一采集与选材核心

**文件：**

- `app/pipeline/news_pipeline.py`
- 复用：`collectors/*`
- `aggregator/merger.py`

- [ ] **步骤 1：统一候选输入来源**

要求：

1. 正式主链路的候选项必须来自统一 collector 组合
2. 不允许长期并行维护“新服务 RSS-only 主链路”和“旧 collector 主链路”
3. publish pipeline 读取候选的唯一入口必须是 `Ingestion Store.load_window_candidates`

- [ ] **步骤 2：统一选材逻辑**

要求：

1. 最终选材必须统一走 `Merger`
2. 不再只依赖当前服务里的简单 top5 逻辑

- [ ] **步骤 3：来源失败保持局部容错**

要求：

1. 单个来源失败不得直接导致整轮主流程失败
2. 必须延续旧体系的局部容错语义

---

## 任务 4：新增主题桶与规则轻分类

**文件：**

- 新增：`app/classifiers/topic_classifier.py`
- `aggregator/merger.py`
- `tests/test_topic_classifier.py`

- [ ] **步骤 1：冻结主题桶定义**

本轮至少包含：

1. `model_release`
2. `agent_workflow`
3. `developer_tooling`
4. `research_benchmark`
5. `infrastructure`
6. `application_case`

- [ ] **步骤 2：实现规则轻分类**

规则来源：

1. 来源类型
2. 标题关键词
3. 摘要关键词

要求：

1. 本轮不引入独立 LLM 分类调用
2. 分类结果必须可解释、可测试

- [ ] **步骤 3：给 item 附加分类结果**

要求：

1. 分类结果必须能进入评分逻辑
2. 分类结果至少包含 `topic`

---

## 任务 5：评分系统轻量升级

**文件：**

- `aggregator/merger.py`
- 可能新增：评分辅助模块
- `tests/test_merger.py`

- [ ] **步骤 1：冻结新评分结构**

必须遵守：

```text
final_score =
  source_weight
  + topic_weight
  + keyword_bonus
  + time_modifier
```

- [ ] **步骤 2：关键词降级**

要求：

1. 关键词命中不再是主评分信号
2. 关键词仅作为辅助加分项

- [ ] **步骤 3：来源和主题成为主信号**

要求：

1. 评分必须体现来源分层
2. 评分必须体现主题桶优先级

- [ ] **步骤 4：冻结评分实现细则**

要求：

1. `topic_weight` 必须有明确归属字段
2. `keyword_bonus` 固定为布尔加分，命中时加 `0.5`
3. `topic_confidence` 本轮不参与分值
4. `time_modifier` 固定复用 `collectors.base.time_modifier(pub_date, "morning")`
5. `source_weight` 固定映射：
   - `huggingface = 4.0`
   - `qbitai = 3.0`
   - 其他进入本轮 `ai_only` 发布范围的 RSS AI 垂类来源 = `3.0`
6. `topic_weight` 固定映射：
   - `model_release = 3.0`
   - `agent_workflow = 2.5`
   - `developer_tooling = 2.0`
   - `research_benchmark = 2.0`
   - `infrastructure = 1.5`
   - `application_case = 1.0`
7. 旧 `Merger` 的“每源至少 1 条”保底规则本轮不保留

---

## 任务 6：统一微信端推送样式

**文件：**

- 新增：`app/renderers/wecom_markdown.py`
- 复用：`pusher/wecom.py`
- `tests/test_wecom_markdown_renderer.py`

- [ ] **步骤 1：冻结消息结构**

要求：

1. 统一输出为一条消息
2. 使用 markdown
3. 标题超链接
4. 不展示裸长链接

- [ ] **步骤 2：渲染责任收归程序端**

要求：

1. LLM 不直接输出最终推送格式
2. 程序端统一渲染 markdown 模板

- [ ] **步骤 3：切换正式推送器**

要求：

1. 正式主链路统一使用 WeCom markdown 推送能力
2. 不再以 `text` 作为主发布形态

---

## 任务 7：统一状态持久化

**文件：**

- `infra/storage/state_store.py`
- `app/pipeline/news_pipeline.py`
- `tests/test_state_store.py`

- [ ] **步骤 1：接入 `StateStore`**

要求：

1. 正式主链路必须落盘 `pushed_urls`
2. 正式主链路必须写日报 JSON
3. digest JSON 必须同时落盘 `published_urls` 与 `published_keys`

- [ ] **步骤 2：保留部分成功语义**

要求：

1. 不允许成功推送的结果因后续失败完全丢失
2. 必须保留旧体系的部分成功持久化语义

---

## 任务 8：统一部署与验证文档

**文件：**

- `README.md`
- `docs/operations/deploy/server-guide.md`
- `docker-compose.yml`
- `docker-compose.verify.yml`

- [ ] **步骤 1：统一正式部署口径**

要求：

1. 正式环境只保留 `.env + docker-compose.yml`
2. 验证环境只保留 `.env.verify + docker-compose.verify.yml`

- [ ] **步骤 2：清理双链路心智**

要求：

1. 文档中不得继续把旧 CLI 描述为正式主路径
2. 必须明确服务化入口才是正式发布流程

- [ ] **步骤 3：保留验证闭环**

要求：

1. 验证环境必须支持不触达真实企微客户端的闭环验证
2. 文档中必须明确验证步骤

---

## 审查关卡

### 契约审查

必须检查：

1. 是否只保留了一条正式发布主链路
2. 是否统一为 markdown 推送
3. 是否评分已体现主题桶与关键词降级
4. 是否部署文档已收敛到统一服务口径
5. 是否已引入候选池并做到“高频入池、发布读池”

### 质量审查

必须检查：

1. 是否避免顺手引入数据库
2. 是否避免顺手扩大量来源
3. 是否避免让 LLM 直接控制最终渲染格式
4. 是否保留了状态落盘和局部容错能力
5. 是否避免把候选池误做成数据库化扩展

---

## 最终验证

必须至少验证：

```bash
venv/bin/pytest -q tests/test_news_agent.py tests/test_app_llm.py tests/test_state_store.py
venv/bin/pytest -q tests/test_topic_classifier.py tests/test_wecom_markdown_renderer.py
venv/bin/pytest -q tests/test_ingestion_store.py
docker compose --env-file .env.verify -f docker-compose.yml -f docker-compose.verify.yml config
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/run/news
```

还必须验证：

```bash
rg -n "send_text\\(|msgtype\": \"text\"" app tests
rg -n "news_pipeline" app/main.py app/agents
rg -n "IngestionStore|candidates.jsonl|data/ingestion" app tests
rg -n "load_window_candidates|append_or_merge|ingest job|scheduler" app tests
cat data/$(date +%F)/*.json
find data/ingestion -maxdepth 3 -type f | sort
docker logs mock-wecom --tail=100
```

验证通过标准：

1. 正式主链路可运行
2. 微信端输出为一条 markdown 摘要
3. 状态持久化仍有效
4. 评分逻辑已体现新规则
5. `/run/news` 已真正走统一 pipeline
6. mock webhook 收到的是 markdown payload
7. 状态文件结构符合冻结后的 digest 契约
8. 高频抓取结果已落入文件型候选池
9. 正式发布读取的是候选池，而不是发布时直接全量抓取
10. 自动化测试已证明 publish pipeline 消费的是 `Ingestion Store.load_window_candidates()`，而不是直接调用 collector 全量抓取
11. 自动化测试已证明 ingest job 会把抓取结果写入 `Ingestion Store.append_or_merge()`

---

## 结论

Task006 的成功标准不是“功能更多”，而是：

1. 项目正式主链路已经统一
2. 微信端样式已经统一
3. 状态与部署口径已经统一
4. 评分信号已经从“强依赖关键词命中”升级为“来源分层 + 主题桶 + 关键词辅助”
5. 高频抓取与正式发布已经通过文件型候选池解耦
