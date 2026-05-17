# AI 助手服务实施计划

> **给执行开发的 agent：** 必须按任务逐项执行。推荐使用子 agent 分工开发，并在每个任务完成后先做契约审查，再做质量审查。任务使用 `- [ ]` 复选框跟踪。

**目标：** 在当前 `Claw_news` 仓库内新增一个可部署的服务化 MVP，支持 RSS 抓取、OpenAI-compatible LLM 摘要、企业微信 text 推送、FastAPI 手动触发和 APScheduler 定时任务，同时不破坏现有 CLI 链路，并明确旧部署方式向新服务部署方式的迁移路径。

**架构：** 保留 `main.py` 作为旧 CLI 入口，在 `app/` 下新增服务化入口。新服务通过 `news_agent` 串联 `crawler -> llm -> wecom`，HTTP 与 scheduler 共用同一执行内核，并通过统一运行锁避免并发重入。现有 collector、状态存储和容错经验按适配方式复用，不直接复用 CLI 退出语义。

**技术栈：** Python 3.11、FastAPI、APScheduler、httpx、feedparser、pytest、pytest-asyncio、Docker、docker-compose

---

## 文件结构

本计划默认创建或修改以下文件。

**新增：**
- `app/__init__.py`
- `app/main.py`
- `app/config.py`
- `app/agents/__init__.py`
- `app/agents/news_agent.py`
- `app/tools/__init__.py`
- `app/tools/crawler.py`
- `app/tools/llm.py`
- `app/tools/wecom.py`
- `app/scheduler/__init__.py`
- `app/scheduler/jobs.py`
- `tests/test_app_config.py`
- `tests/test_app_crawler.py`
- `tests/test_app_llm.py`
- `tests/test_app_wecom.py`
- `tests/test_news_agent.py`
- `tests/test_app_api.py`
- `Dockerfile`
- `docker-compose.yml`

**修改：**
- `.env.example`
- `README.md`
- `pyproject.toml`
- `requirements.txt`
- `deploy.example.sh`

**按需适配，不是默认必改：**
- `collectors/rss_sources.py`
- `collectors/utils.py`
- `infra/storage/state_store.py`
- `aggregator/merger.py`

---

## Agent 分工

### Agent 1：配置 + LLM

**负责文件：**
- `app/config.py`
- `app/tools/llm.py`
- `tests/test_app_config.py`
- `tests/test_app_llm.py`
- `.env.example`

### Agent 2：抓取 + 排序 + 任务内核

**负责文件：**
- `app/tools/crawler.py`
- `app/agents/news_agent.py`
- `tests/test_app_crawler.py`
- `tests/test_news_agent.py`
- 按需适配：`collectors/rss_sources.py`
- 按需适配：`collectors/utils.py`
- 按需复用：`aggregator/merger.py`

### Agent 3：WeCom + Scheduler + API + 部署

**负责文件：**
- `app/tools/wecom.py`
- `app/scheduler/jobs.py`
- `app/main.py`
- `tests/test_app_wecom.py`
- `tests/test_app_api.py`
- `Dockerfile`
- `docker-compose.yml`
- `README.md`
- `requirements.txt`
- `pyproject.toml`
- `deploy.example.sh`

### 审查 Agent

1. 契约审查 Agent
   - 只检查是否符合 `spec/task003/spec.md`
2. 质量审查 Agent
   - 只检查代码质量、测试完整性、文档一致性

---

## 任务 1：冻结服务边界

**文件：**
- 只读：`spec/task003/spec.md`
- 只读：`docs/superpowers/specs/2026-05-17-ai-assistant-service-design.md`
- 只读：`docs/superpowers/specs/2026-05-17-ai-assistant-service-design-review.md`
- 修改：`README.md`

- [ ] **步骤 1：开发前先复核不可变范围**

阅读：
- `spec/task003/spec.md`
- `docs/superpowers/specs/2026-05-17-ai-assistant-service-design.md`
- `docs/superpowers/specs/2026-05-17-ai-assistant-service-design-review.md`

预期：
- 明确本轮是“同仓双入口”
- 明确不改造现有 CLI 语义
- 明确 LLM 为 OpenAI-compatible
- 明确部署存在“内部 scheduler”与“外部 HTTP 调度”两种模式，但本轮推荐前者
- 明确候选新闻 `10` 条、最终展示 `5` 条、每条标题带原文链接
- 明确复用原项目 RSS 评分逻辑

- [ ] **步骤 2：先为 README 预留服务模式章节**

目标章节：
- `Service Mode`
- `Environment Variables`
- `Docker Deployment`
- `HTTP Endpoints`
- `Deployment Modes`

预期：
- README 结构先预留，后续任务填充内容

- [ ] **步骤 3：提交边界冻结结果**

```bash
git add spec/task003/spec.md docs/superpowers/specs/2026-05-17-ai-assistant-service-design.md docs/superpowers/specs/2026-05-17-ai-assistant-service-design-review.md README.md
git commit -m "docs: freeze service architecture boundaries"
```

---

## 任务 2：补充服务依赖

**文件：**
- 修改：`pyproject.toml`
- 修改：`requirements.txt`

- [ ] **步骤 1：先确认缺失依赖**

预期缺失依赖：
- `fastapi`
- `uvicorn`
- `apscheduler`

执行：

```bash
rg -n "fastapi|uvicorn|apscheduler" pyproject.toml requirements.txt
```

预期：
- 不存在或不完整

- [ ] **步骤 2：增加最小运行时依赖**

必须增加：

```text
fastapi
uvicorn
apscheduler
```

规则：
- 不引入 OpenAI 官方 SDK
- LLM 调用继续基于 `httpx`

- [ ] **步骤 3：验证依赖元数据一致**

执行：

```bash
python -m pip install -e ".[dev]"
```

预期：
- 安装成功

- [ ] **步骤 4：提交依赖变更**

```bash
git add pyproject.toml requirements.txt
git commit -m "build: add service runtime dependencies"
```

---

## 任务 3：实现配置层

**文件：**
- 新增：`app/config.py`
- 新增：`tests/test_app_config.py`
- 修改：`.env.example`

- [ ] **步骤 1：先写配置解析失败测试**

测试必须覆盖：
- 必填 `LLM_API_KEY`
- 必填 `LLM_BASE_URL`
- 必填 `LLM_MODEL`
- 必填 `WECOM_WEBHOOK_URL`
- 默认 `TZ`
- `NEWS_RSS_URLS` 解析

执行：

```bash
pytest tests/test_app_config.py -v
```

预期：
- 因模块不存在或未实现而失败

- [ ] **步骤 2：实现最小配置对象**

建议结构：

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class AppConfig:
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    wecom_webhook_url: str
    tz: str
    news_rss_urls: list[str]
```

必须提供：

```python
def load_config() -> AppConfig: ...
```

行为要求：
- 从环境变量读取
- 缺关键配置时报 `ValueError`
- `TZ` 固定默认一个值，建议 `Asia/Shanghai`

- [ ] **步骤 3：更新 `.env.example`**

至少包含：

```dotenv
LLM_API_KEY=
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4.1-mini
WECOM_WEBHOOK_URL=
TZ=Asia/Shanghai
NEWS_RSS_URLS=
```

- [ ] **步骤 4：运行测试**

```bash
pytest tests/test_app_config.py -v
```

预期：
- 通过

- [ ] **步骤 5：提交配置层**

```bash
git add app/config.py tests/test_app_config.py .env.example
git commit -m "feat: add service environment config"
```

---

## 任务 4：实现 RSS 抓取器

**文件：**
- 新增：`app/tools/crawler.py`
- 新增：`tests/test_app_crawler.py`
- 按需修改：`collectors/rss_sources.py`

- [ ] **步骤 1：先写抓取行为失败测试**

测试必须覆盖：
- 解析多个 RSS 源
- 按链接去重
- 候选最多保留 `10` 条
- 输出字段标准化
- 单个 RSS 源失败时跳过

执行：

```bash
pytest tests/test_app_crawler.py -v
```

预期：
- 因模块不存在或未实现而失败

- [ ] **步骤 2：以适配方式实现抓取器**

必须提供：

```python
async def fetch_news(rss_urls: list[str], limit: int = 10) -> list[dict]: ...
```

输出项结构：

```python
{
    "title": "...",
    "link": "...",
    "summary": "...",
    "published_at": "...",
}
```

规则：
- 允许复用 `collectors/rss_sources.py` 的解析逻辑
- 不直接依赖 CLI 配置对象
- 失败源只记日志并跳过
- 若 `feedparser.parse()` 仍为同步调用，则必须放入线程池
- 本层返回候选新闻，默认上限 `10`

- [ ] **步骤 3：运行测试**

```bash
pytest tests/test_app_crawler.py -v
```

预期：
- 通过

- [ ] **步骤 4：提交抓取层**

```bash
git add app/tools/crawler.py tests/test_app_crawler.py collectors/rss_sources.py
git commit -m "feat: add service rss crawler"
```

---

## 任务 5：实现 LLM 客户端

**文件：**
- 新增：`app/tools/llm.py`
- 新增：`tests/test_app_llm.py`

- [ ] **步骤 1：先写摘要生成失败测试**

测试必须覆盖：
- 正常摘要响应
- 空新闻回退
- 上游 HTTP 错误
- 模型输出格式异常

执行：

```bash
pytest tests/test_app_llm.py -v
```

预期：
- 因模块不存在或未实现而失败

- [ ] **步骤 2：实现 OpenAI-compatible 客户端**

必须提供：

```python
async def summarize_news(items: list[dict], *, base_url: str, api_key: str, model: str) -> str: ...
```

规则：
- 使用 `httpx`
- 不依赖供应商私有 SDK
- 输出必须是中文
- 空新闻时返回确定性的可推送说明

提示词约束：
- 标题为 `今日 AI 新闻摘要`
- 每条包含 `核心内容` / `重要性` / `趋势判断`
- 文末包含 `今日一句话判断`
- 每条标题必须保留原文链接
- 摘要基于最终 `5` 条新闻生成，不是对全部候选都展开

- [ ] **步骤 3：运行测试**

```bash
pytest tests/test_app_llm.py -v
```

预期：
- 通过

- [ ] **步骤 4：提交 LLM 层**

```bash
git add app/tools/llm.py tests/test_app_llm.py
git commit -m "feat: add openai-compatible llm summarizer"
```

---

## 任务 6：实现 WeCom 文本推送器

**文件：**
- 新增：`app/tools/wecom.py`
- 新增：`tests/test_app_wecom.py`

- [ ] **步骤 1：先写文本推送失败测试**

测试必须覆盖：
- 成功响应
- 业务错误
- HTTP 错误
- 超长消息截断或分段

执行：

```bash
pytest tests/test_app_wecom.py -v
```

预期：
- 因模块不存在或未实现而失败

- [ ] **步骤 2：实现文本推送客户端**

必须提供：

```python
async def send_text(webhook_url: str, content: str) -> dict: ...
```

规则：
- 使用 WeCom text 消息
- 处理超长内容
- 明确抛出网络与业务错误

- [ ] **步骤 3：运行测试**

```bash
pytest tests/test_app_wecom.py -v
```

预期：
- 通过

- [ ] **步骤 4：提交推送层**

```bash
git add app/tools/wecom.py tests/test_app_wecom.py
git commit -m "feat: add service wecom text pusher"
```

---

## 任务 7：实现任务内核

**文件：**
- 新增：`app/agents/news_agent.py`
- 新增：`tests/test_news_agent.py`
- 按需复用：`aggregator/merger.py`

- [ ] **步骤 1：先写编排失败测试**

测试必须覆盖：
- 成功路径
- 无新闻路径
- 抓取失败路径
- LLM 失败路径
- 推送失败路径
- 锁冲突路径
- 候选 `10` 条经过排序后只选 `5` 条进入摘要
- 最终输出中的每条标题保留原文链接

执行：

```bash
pytest tests/test_news_agent.py -v
```

预期：
- 因模块不存在或未实现而失败

- [ ] **步骤 2：实现任务编排内核**

必须提供：

```python
class NewsAgent:
    async def run_once(self) -> dict: ...
```

行为要求：
- 记录每个阶段日志
- 调用 crawler
- 调用 llm
- 调用 wecom
- 返回结构化结果
- 如果运行锁已被占用，返回 skipped 结果
- 失败时尝试推送错误摘要
- 复用原项目 RSS 评分逻辑完成候选排序
- 候选新闻最多 `10` 条，最终发送给 LLM 的新闻固定为 `5` 条

- [ ] **步骤 3：运行测试**

```bash
pytest tests/test_news_agent.py -v
```

预期：
- 通过

- [ ] **步骤 4：提交任务内核**

```bash
git add app/agents/news_agent.py tests/test_news_agent.py aggregator/merger.py
git commit -m "feat: add news agent orchestration"
```

---

## 任务 8：实现 Scheduler 与 FastAPI 入口

**文件：**
- 新增：`app/scheduler/jobs.py`
- 新增：`app/main.py`
- 新增：`tests/test_app_api.py`

- [ ] **步骤 1：先写 API 与 scheduler 失败测试**

测试必须覆盖：
- `GET /health`
- `GET /`
- `POST /run/news`
- scheduler 注册 `09:00`、`14:00`、`20:00`
- 启动时不会重复注册任务

执行：

```bash
pytest tests/test_app_api.py -v
```

预期：
- 因模块不存在或未实现而失败

- [ ] **步骤 2：实现 scheduler**

行为要求：
- 注册三个 cron 时间点
- 应用统一时区
- 提供 `start_scheduler()` 与 `stop_scheduler()`
- scheduler 启用策略可配置，避免开发与生产期双重触发

- [ ] **步骤 3：实现 FastAPI 应用**

必须提供接口：

```text
GET  /
GET  /health
POST /run/news
```

规则：
- 启动时加载 scheduler
- 关闭时停止 scheduler
- 路由只委派给 `NewsAgent`
- 路由体内不写业务逻辑

- [ ] **步骤 4：运行测试**

```bash
pytest tests/test_app_api.py -v
```

预期：
- 通过

- [ ] **步骤 5：提交入口层**

```bash
git add app/scheduler/jobs.py app/main.py tests/test_app_api.py
git commit -m "feat: add fastapi entry and scheduler"
```

---

## 任务 9：补充 Docker 部署

**文件：**
- 新增：`Dockerfile`
- 新增：`docker-compose.yml`
- 修改：`README.md`
- 修改：`deploy.example.sh`

- [ ] **步骤 1：先写部署检查清单**

至少包含：
- 单进程 uvicorn
- `.env` 注入
- `8000` 端口映射
- `restart: always`
- 若使用文件状态则挂载 `data/`
- 明确是否启用内部 scheduler
- 明确若继续沿用服务器外部调度，应调用 `POST /run/news`

- [ ] **步骤 2：实现 Docker 资产**

必须启动命令：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

规则：
- 不配置多 worker
- 优先 slim 镜像
- 若默认启用内部 scheduler，则必须写明“单实例运行”

- [ ] **步骤 3：更新 README**

必须写清楚：
- 如何复制 `.env.example` 为 `.env`
- 如何配置 LLM 与 WeCom
- 如何 `docker compose up -d --build`
- 如何调用 `/health`
- 如何调用 `POST /run/news`
- 如何查看日志
- 旧项目也是服务器定时触发，本次变化的是触发形态，不是是否定时
- 两种部署模式：
  - 模式 A：服务内 APScheduler
  - 模式 B：服务器外部定时调用 HTTP
- 本轮推荐模式 A，迁移期可先用模式 B

- [ ] **步骤 4：更新部署参考脚本**

`deploy.example.sh` 至少说明：
- 旧 CLI 仍可用于验证
- 新服务如何启动
- 如果采用外部定时调用 HTTP，应如何配置
- 该脚本只是参考模板，不等于唯一生产方案

- [ ] **步骤 5：验证 compose**

```bash
docker compose config
```

预期：
- 通过

- [ ] **步骤 6：提交部署文档与资产**

```bash
git add Dockerfile docker-compose.yml README.md deploy.example.sh
git commit -m "docs: add service deployment assets"
```

---

## 任务 10：全量验证

**文件：**
- 审查所有本轮变更文件

- [ ] **步骤 1：运行目标测试**

```bash
pytest tests/test_app_config.py tests/test_app_crawler.py tests/test_app_llm.py tests/test_app_wecom.py tests/test_news_agent.py tests/test_app_api.py -v
```

预期：
- 通过

- [ ] **步骤 2：运行完整测试**

```bash
pytest -q
```

预期：
- 通过

- [ ] **步骤 3：做旧 CLI 回归验证**

```bash
python main.py --period morning --dry-run
```

预期：
- 正常运行，不因新服务引入回归

- [ ] **步骤 4：做服务冒烟验证**

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/
curl -X POST http://127.0.0.1:8000/run/news
```

预期：
- `/health` 返回 200
- `/` 返回 200
- `/run/news` 返回可解释结果

- [ ] **步骤 5：做容器冒烟验证**

```bash
docker compose config
```

预期：
- 通过

- [ ] **步骤 6：提交验证相关更新**

```bash
git add .
git commit -m "test: verify ai assistant service integration"
```

---

## 审查关卡

### 关卡 1：契约一致性审查

每个任务完成后，契约审查 Agent 必须确认：

1. 未破坏现有 CLI
2. 未引入数据库、向量库、微信回调
3. LLM 为 OpenAI-compatible
4. API、scheduler、agent 共用一套任务内核
5. 部署仍是单活模型
6. 候选 `10` 条、最终展示 `5` 条的设计未被改坏
7. 每条标题都保留原文链接
8. 复用了原项目 RSS 评分逻辑

### 关卡 2：质量审查

每个任务完成后，质量审查 Agent 必须确认：

1. 测试充分
2. 路由层无业务逻辑
3. 代码边界清晰
4. 文档与行为一致
5. 没有写死 OpenAI 官方供应商

### 关卡 3：最终审查

最终 reviewer 必须按以下顺序审查：

1. `spec/task003/spec.md`
2. `docs/superpowers/specs/2026-05-17-ai-assistant-service-design.md`
3. `docs/superpowers/specs/2026-05-17-ai-assistant-service-design-review.md`
4. `docs/superpowers/specs/2026-05-17-ai-assistant-service-one-page.md`
5. 所有新增测试
6. Docker、README、`deploy.example.sh`

---

## 执行中必须持续检查的阻塞风险

1. `app/` 路径中出现 `sys.exit()`
2. 默认启用多 worker scheduler
3. 写死 OpenAI 官方域名
4. API 与 scheduler 使用不同锁
5. 文档没有同步更新
6. 没有明确部署模式切换与迁移关系

---

## 计划自检

### 契约覆盖检查

本计划已覆盖：

1. `app/` 服务目录
2. env 配置
3. RSS 抓取
4. OpenAI-compatible LLM
5. WeCom text 推送
6. `NewsAgent`
7. FastAPI
8. APScheduler
9. Docker
10. README
11. 旧 CLI 回归验证
12. 候选 `10` 条、最终展示 `5` 条
13. 原文跳转链接
14. 原项目 RSS 评分逻辑复用

### 占位符检查

未使用 `TBD`、`TODO`、`implement later` 等占位语。

### 命名一致性检查

计划中统一使用：

1. `load_config()`
2. `fetch_news()`
3. `summarize_news()`
4. `send_text()`
5. `NewsAgent.run_once()`

后续实现应保持这些命名一致，除非先回改设计文档和计划文档。
