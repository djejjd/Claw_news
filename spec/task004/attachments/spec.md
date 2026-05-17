# Claw_news M5 Task Contract Spec

## Immutable Rule

本文件是当前任务的唯一验收契约。
自确认后：

1. Review 只能基于本文件判断是否通过。
2. Review 不允许提出新的范围外阻塞项。
3. 新发现但不属于本文件范围的问题，必须记录到 `next_task`，不得阻塞当前任务。
4. 阻塞项必须能映射到本文件的“实现要求”或“验收标准”。
5. 禁止使用“建议优化”“最好”“可以考虑”作为阻塞理由。

---

## 任务目标

在 Task003 已完成服务化 MVP 的基础上，完成“交付完善”：

1. 保证企业微信中新闻标题对应的信息源链接可直接使用
2. 为内部 scheduler 增加显式开关，明确区分两种部署模式
3. 补齐服务模式的验证链路与 CI / 文档一致性

---

## 修改范围

本轮允许修改以下内容：

1. 服务推送层
   - `app/tools/wecom.py`
   - `app/tools/llm.py`
   - `app/agents/news_agent.py`

2. 服务配置与入口
   - `app/config.py`
   - `app/main.py`
   - `app/scheduler/jobs.py`
   - `.env.example`

3. 依赖与工程化
   - `pyproject.toml`
   - `requirements.txt`
   - `.github/workflows/ci.yml`

4. 部署与文档
   - `README.md`
   - `deploy.example.sh`
   - `Dockerfile`
   - `docker-compose.yml`

5. 测试
   - `tests/test_app_wecom.py`
   - `tests/test_app_llm.py`
   - `tests/test_news_agent.py`
   - `tests/test_app_api.py`
   - 为本轮目标新增或调整的服务模式测试

---

## 禁止修改范围

本轮禁止：

1. 重写旧 CLI 主流程
   - `main.py`
   - `aggregator/merger.py` 的既有评分规则

2. 扩展新业务能力
   - 微信回调
   - 数据库
   - 向量库
   - 多 Agent 运行时框架
   - 前端页面

3. 改造当前任务目标之外的服务边界
   - 不做多 key 自动切换
   - 不做预算调度
   - 不做 provider 专用适配层

---

## 实现要求

### 1. 链接可用性契约

1. 企业微信收到的每条新闻必须能直接访问原文信息源。
2. 如果继续使用 `text` 消息，则每条标题后必须显式展示原文 URL。
3. 如果切换到 `markdown` 消息，则必须验证企业微信中链接可点击。
4. 不允许仅保留 `[标题](链接)` 这种在目标消息类型中不可点击的形式。

### 2. 调度模式契约

1. 新服务必须增加显式配置开关，例如 `ENABLE_INTERNAL_SCHEDULER`。
2. 当开关为启用时：
   - 启动服务即注册并启动内部 scheduler
3. 当开关为禁用时：
   - 服务只提供 HTTP 接口
   - 不启动内部 scheduler
4. README 与 `deploy.example.sh` 必须明确说明两种模式：
   - 模式 A：内部 scheduler
   - 模式 B：服务器外部定时调用 HTTP

### 3. 验证闭环契约

1. 本轮必须确保服务模式相关依赖进入可测试环境。
2. CI 必须覆盖服务模式新增测试。
3. 必须至少具备以下验证能力：
   - `GET /health`
   - `POST /run/news`
   - scheduler 开关启停行为
4. 文档中的命令必须与实际代码行为一致。

### 4. 文档契约

1. `README.md` 必须写清楚：
   - 如何复制 `.env.example`
   - 如何配置 `ENABLE_INTERNAL_SCHEDULER`
   - 内部 scheduler 与外部 HTTP 调度的差异
   - 如何验证原文链接可用
2. `.env.example` 必须覆盖本轮新增配置项。
3. `deploy.example.sh` 必须体现两种部署模式的差异。

---

## 验收标准

### A. 链接可用

1. 服务推送消息中的每条新闻都能直接访问原文。
2. 测试覆盖链接输出格式。

### B. 调度开关成立

1. 存在显式 scheduler 开关配置。
2. 开启时服务自动调度。
3. 关闭时服务不自动调度，只保留 HTTP 触发。

### C. 验证闭环成立

1. 服务相关测试可在标准测试环境中运行。
2. CI 覆盖服务模式测试。
3. README / 部署脚本 / 实际行为一致。

### D. 无回归

1. Task003 的服务主链路不被破坏。
2. 旧 CLI 入口不被移除。

---

## 测试命令

```bash
pytest -q
python main.py --period morning --dry-run
uvicorn app.main:app --host 0.0.0.0 --port 8000
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/run/news
docker compose config
```

---

## Review Checklist

1. 推送消息中的原文链接是否真正可用
2. 是否增加了显式 scheduler 开关
3. 是否支持“内部 scheduler / 外部 HTTP 调度”两种模式
4. README、`.env.example`、`deploy.example.sh` 是否同步更新
5. CI 是否覆盖服务模式测试
6. 旧 CLI 是否未回归

---

## 非本轮范围

以下内容只能进入后续 `next_task`，不得阻塞当前任务：

1. 多 key 轮询
2. 预算调度
3. provider 专用适配层
4. 数据库存储
5. Web 管理后台
6. 更多 source 的扩展

---

## next_task

（预留）
