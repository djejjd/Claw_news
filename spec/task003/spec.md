# Claw_news M4 Task Contract Spec

## Immutable Rule

本文件是当前任务的唯一验收契约。
自确认后：

1. Review 只能基于本文件判断是否通过。
2. Review 不允许提出新的范围外阻塞项。
3. 新发现但不属于本文件范围的问题，必须记录到 `next_task`，不得阻塞当前任务。
4. 阻塞项必须能映射到本文件的“实现要求”或“验收标准”。
5. 禁止使用“建议优化”“最好”“可以考虑”作为阻塞理由。

---

## 方案决策

本轮结论：**融合到当前仓库，而不是独立成新项目。**

采用方案：**同仓双入口**

1. 保留现有 `main.py` 批处理热点推送链路，不做破坏式改造。
2. 在当前仓库新增 `app/` 服务化入口，实现 `FastAPI + APScheduler + OpenAI-compatible LLM + 企业微信机器人` 的个人 AI 助手 MVP。
3. 新服务优先复用现有仓库中已经稳定的 RSS 抓取、企业微信推送、容错和测试经验；不要求本轮统一两套配置体系。

选择该方案的原因：

1. 当前仓库已具备 RSS 采集、推送、状态管理、测试基础，直接复用成本低。
2. `new_design.md` 的核心需求与当前项目高度重叠，拆新仓会重复建设抓取、推送、部署和测试基础设施。
3. 当前项目已有 CLI 批处理使用场景，本轮通过双入口并存可以降低迁移风险。

---

## 任务目标

在不破坏现有 `Claw_news` 热点聚合 CLI 流程的前提下，为当前仓库新增一个可独立运行的服务化 MVP：

1. 支持按配置抓取 RSS 新闻。
2. 调用 OpenAI-compatible 模型生成中文摘要分析。
3. 将摘要结果推送到企业微信群机器人。
4. 提供 `FastAPI` HTTP 接口用于健康检查与手动触发。
5. 提供 `APScheduler` 定时任务用于自动运行。
6. 提供 `Dockerfile` 与 `docker-compose.yml` 用于 Linux 服务器部署。

---

## 修改范围

本轮允许修改以下内容：

1. 新增服务目录
   - `app/main.py`
   - `app/config.py`
   - `app/agents/news_agent.py`
   - `app/tools/llm.py`
   - `app/tools/wecom.py`
   - `app/tools/crawler.py`
   - `app/scheduler/jobs.py`

2. 依赖与部署
   - `pyproject.toml`
   - `requirements.txt`
   - `Dockerfile`
   - `docker-compose.yml`
   - `.env.example`

3. 文档
   - `README.md`

4. 测试
   - `tests/` 下新增或调整与 `app/` 服务相关的测试

5. 在不改变原有行为的前提下，允许对现有模块做最小复用性调整
   - `collectors/`
   - `pusher/`
   - `infra/`

---

## 禁止修改范围

本轮禁止：

1. 重写现有热点聚合主流程
   - `main.py` 的早报/晚报执行语义
   - `aggregator/merger.py` 的评分与竞争规则

2. 改造现有业务边界为单一统一架构
   - 不要求本轮把旧 CLI 全量迁移到 `FastAPI`
   - 不要求本轮把 YAML 配置体系替换为 env-only

3. 引入超出 MVP 的复杂能力
   - 微信回调
   - 浏览器自动化
   - 数据库
   - 向量库
   - 多 Agent 编排框架
   - 用户鉴权系统
   - 前端页面

4. 破坏现有推送格式与现有 collector 行为
   - 不修改当前 CLI 的既有消息格式作为本轮目标
   - 不因服务化而删除现有 `huggingface`、`taptap`、`rss` 采集链路

---

## 实现要求

### 1. 架构契约

1. 当前仓库必须同时保留两个入口：
   - 旧入口：`python main.py --period morning|evening [--dry-run]`
   - 新入口：`uvicorn app.main:app --host 0.0.0.0 --port 8000`
2. 新服务必须以 `app/` 目录实现，不得把服务代码直接堆叠回现有 `main.py`。
3. 新服务与旧 CLI 可以共存，但本轮不要求统一配置对象、统一消息模板、统一调度入口。

### 2. 配置契约

1. 新服务通过环境变量读取配置，至少包括：
   - `LLM_API_KEY`
   - `LLM_BASE_URL`
   - `LLM_MODEL`
   - `WECOM_WEBHOOK_URL`
   - `TZ`
   - `NEWS_RSS_URLS`
2. `.env.example` 必须覆盖上述变量，并给出默认示例值。
3. 新服务缺少关键配置时必须在启动或执行时给出明确错误，不允许静默失败。
4. 旧 CLI 的 `config.yaml` 与 `PUSHER_WECOM_WEBHOOK` 机制必须保持可用。
5. 新服务的 LLM 配置语义必须是“通用兼容接口配置”，不得在实现层把供应商硬编码为仅支持 OpenAI 官方。
6. 兼容目标定义为：可通过 `base_url + api_key + model` 完成调用的 OpenAI-compatible 接口。
7. 本轮允许 README 给出若干供应商示例，但实现契约不得绑定某几个固定厂商。

### 3. 新闻抓取契约

1. `app/tools/crawler.py` 必须输出统一新闻项结构，至少包含：
   - `title`
   - `link`
   - `summary`
   - `published_at`
2. 本轮新服务只要求支持 RSS 抓取。
3. 必须支持多 RSS 源配置。
4. 必须去重，并限制最多返回最近 10 条新闻。
5. 某个 RSS 源失败时不得导致整体任务中断，必须跳过失败源并继续处理其他源。
6. 允许直接复用现有 RSS 能力，或在 `app/tools/crawler.py` 中以适配方式封装复用。

### 4. LLM 契约

1. `app/tools/llm.py` 必须封装明确的 LLM 调用入口，例如 `summarize_news(items)`。
2. 输出必须为中文。
3. 输出内容必须包含：
   - 标题区：`今日 AI 新闻摘要`
   - 至少 1 条新闻摘要条目
   - 每条包含“核心内容”“重要性”“趋势判断”
   - 结尾包含“今日一句话判断”
4. 当无新闻可总结时，必须返回明确可推送的空结果说明，而不是抛出未处理异常。
5. LLM 客户端必须基于 OpenAI-compatible HTTP 协议实现，不要求本轮分别适配各家私有 SDK。
6. 本轮不要求实现多 key 轮询、预算调度、失败回退或 provider 专用分支逻辑。

### 5. 企业微信推送契约

1. `app/tools/wecom.py` 必须从 `WECOM_WEBHOOK_URL` 读取推送地址。
2. 必须支持 text 消息推送。
3. 当消息超长时，必须进行截断或分段，保证不会因单条超长直接失败。
4. 网络异常、HTTP 异常、企业微信业务异常必须被识别并向上抛出可处理错误。

### 6. Agent 契约

1. `app/agents/news_agent.py` 必须串联：
   - 抓取新闻
   - LLM 总结
   - 推送到企业微信
2. 必须记录关键日志，至少覆盖：
   - 开始抓取
   - 抓取完成
   - 开始总结
   - 总结完成
   - 开始推送
   - 推送完成或失败
3. 当执行失败时，必须向企业微信群推送错误摘要，前提是 webhook 已配置可用。

### 7. 调度与 API 契约

1. `app/main.py` 必须提供以下接口：
   - `GET /health` 返回可判定健康状态
   - `GET /` 返回项目状态说明
   - `POST /run/news` 手动触发新闻任务
2. `app/scheduler/jobs.py` 必须使用 `APScheduler` 注册定时任务。
3. 默认调度时间必须包含：
   - `09:00`
   - `14:00`
   - `20:00`
4. 时区必须可通过 `TZ` 配置，默认值允许为 `Asia/Tokyo` 或 `Asia/Shanghai`，但实现中必须固定采用其中一个默认值并在 README 说明。

### 8. 部署契约

1. 必须提供 `Dockerfile`。
2. 必须提供 `docker-compose.yml`。
3. 容器启动命令必须运行：
   - `uvicorn app.main:app --host 0.0.0.0 --port 8000`
4. `docker-compose.yml` 必须包含：
   - `restart: always`
   - `8000` 端口映射
   - `.env` 注入方式

### 9. 文档契约

1. `README.md` 必须同时说明旧 CLI 模式与新服务模式。
2. README 至少包含：
   - 如何复制 `.env.example` 为 `.env`
   - 如何填写 LLM API Key / Base URL / Model 与企业微信 Webhook
   - 如何使用 `docker compose up -d --build` 启动
   - 如何调用 `/health`
   - 如何手动调用 `/run/news`
   - 如何查看容器日志
3. README 中不得把微信回调、浏览器自动化、数据库等非本轮能力写成已支持功能。
4. README 必须明确说明：只要服务提供 OpenAI-compatible 接口，即可通过修改 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL` 接入。

---

## 验收标准

### A. 方案边界正确

1. 仓库内同时存在旧 CLI 入口与新 `app/` 服务入口。
2. 现有 `main.py` 仍可作为独立入口保留。
3. 新服务代码位于 `app/` 下，而不是散落到原有批处理入口中。

### B. 新服务可启动

1. `uvicorn app.main:app --host 0.0.0.0 --port 8000` 可以启动应用。
2. `GET /health` 返回 200，响应内容可明确判定为健康。
3. `GET /` 返回 200，且包含项目状态说明。

### C. 新闻任务链路成立

1. `POST /run/news` 可触发一次完整执行。
2. 抓取成功时，任务会进入 LLM 总结与企微推送阶段。
3. 任一 RSS 源失败时，整体任务不会直接崩溃。
4. 无新闻时返回可解释结果。

### D. LLM 与推送行为成立

1. `summarize_news(items)` 的结果为中文。
2. 摘要格式包含“今日 AI 新闻摘要”和“今日一句话判断”。
3. 企业微信超长消息场景有明确处理逻辑。
4. 推送失败能够返回或记录明确错误。
5. 新服务未把 LLM 供应商硬编码为 OpenAI 官方；切换兼容供应商时无需改代码，只需改配置。

### E. 调度与部署成立

1. `APScheduler` 已注册 09:00、14:00、20:00 三个时间点。
2. `Dockerfile` 与 `docker-compose.yml` 存在且命令正确。
3. README 的启动命令与容器实际入口一致。

### F. 旧链路无回归

1. 现有测试在本轮修改后继续通过。
2. 与本轮相关的新测试通过。
3. 旧 CLI 的基础用法未被移除：
   - `python main.py --period morning --dry-run`

---

## 测试命令

```bash
pytest -q
python main.py --period morning --dry-run
uvicorn app.main:app --host 0.0.0.0 --port 8000
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/
curl -X POST http://127.0.0.1:8000/run/news
docker compose config
```

---

## Review Checklist

1. 是否明确采用“同仓融合、双入口”而非独立新仓
2. 旧 `main.py` 是否仍可保留使用
3. `app/` 服务结构是否完整
4. 新服务是否使用 env 配置而不是侵入式替换旧 YAML 体系
5. LLM 配置是否采用 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL` 的通用兼容接口语义
6. RSS 抓取是否支持多源、去重、失败容错、最多 10 条
7. LLM 摘要是否固定中文输出并包含规定结构
8. 企业微信是否支持 text 推送与超长处理
9. `POST /run/news` 是否能触发任务
10. `APScheduler` 是否注册 09:00、14:00、20:00
11. Docker 与 README 是否覆盖服务化部署说明
12. 旧 CLI dry-run 是否未回归

---

## 非本轮范围

以下内容只能进入 `next_task`，不得阻塞当前任务：

1. 将旧 CLI 与新服务彻底统一为一套配置系统
2. 将现有 `main.py` 完整迁移为 service-first 架构
3. 支持企业微信回调或双向对话
4. 引入数据库、任务队列、缓存、向量库
5. 支持多 key 轮询、预算调度、自动回退、provider 专用适配、多模型路由、工具调用、多 Agent
6. Web 管理后台
7. 对现有热点聚合评分模型进行重设计
8. 把 `huggingface`、`taptap` 也接入新服务的首版 MVP

---

## next_task

1. 统一新旧入口的配置抽象
2. 评估是否将现有 RSS collector 进一步提炼为共享适配层
3. 评估把 `huggingface` / `taptap` 以可选 source 的方式接入新服务
4. 评估将 launchd 部署说明下沉为历史模式，只保留 service-first 文档入口
5. 评估是否需要在后续版本引入多 key / 多供应商回退策略
