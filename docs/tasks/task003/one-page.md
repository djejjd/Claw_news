# AI 助手服务一页开发与评审清单

## 1. 本轮目标

在当前 `Claw_news` 仓库中新增一个服务化 MVP，用于：

1. 抓取 RSS 新闻
2. 按现有项目 RSS 评分逻辑排序
3. 选出最值得推送的少量新闻
4. 调用 OpenAI-compatible LLM 生成中文摘要
5. 推送到企业微信群
6. 提供 HTTP 手动触发与定时触发能力

---

## 2. 已定版设计

### 展示数量

1. 每次抓取候选新闻最多 `10` 条
2. 去重并排序后，最终展示 `5` 条

### 排序规则

复用原项目 RSS 评分逻辑，不重新设计排序规则。

本轮复用：

1. `position_score`
2. `keyword_bonus`
3. `time_modifier`

主要来源：

1. `aggregator/merger.py`
2. `collectors/base.py`

### 输出格式

企业微信群摘要采用以下规则：

1. 每条新闻标题直接带原文跳转链接
2. 每条新闻必须包含：
   - 核心内容
   - 重要性
   - 趋势判断
3. 文末给出“今日一句话判断”

推荐格式：

```text
今日 AI 新闻摘要

1. [标题](原文链接)
   - 核心内容：...
   - 重要性：...
   - 趋势判断：...

2. [标题](原文链接)
   - 核心内容：...
   - 重要性：...
   - 趋势判断：...

今日一句话判断：...
```

### 模型接入

本轮只支持 OpenAI-compatible 接口。

配置项：

1. `LLM_API_KEY`
2. `LLM_BASE_URL`
3. `LLM_MODEL`

明确不做：

1. 多 key 轮询
2. 自动回退
3. 预算调度
4. 供应商专用 SDK 适配

### 部署方式

原项目本来就是服务器上定时触发，这一点不变。

变化的是触发形态：

旧方式：

1. 服务器外部定时器
2. 调用 `python main.py`
3. 进程跑完退出

新方式：

1. 服务器部署常驻服务
2. 服务内 `APScheduler` 定时执行
3. 保留 `POST /run/news` 手动触发

本轮正式主路径：

1. 推荐 **内部 scheduler 模式**
2. 迁移期允许继续使用服务器外部定时器调用：

```bash
curl -X POST http://127.0.0.1:8000/run/news
```

### 单活约束

本轮必须是：

1. 单容器
2. 单 worker
3. 单实例
4. API 与 scheduler 共用同一把运行锁

不允许：

1. 多 worker
2. 多副本
3. 外部定时器和内部 scheduler 同时默认启用

---

## 3. 开发边界

### 允许做

1. 新增 `app/` 服务目录
2. 新增 FastAPI、APScheduler、Docker 部署
3. 复用现有 RSS 评分逻辑
4. 复用现有 collector / state store 的经验与部分实现

### 不允许做

1. 引入数据库
2. 引入向量库
3. 引入微信回调
4. 引入浏览器自动化
5. 引入多 Agent 运行时框架
6. 重写旧 CLI 主流程

---

## 4. 本次新增且必须先阅读的文档

1. 契约 spec
   - [spec/task003/contract.md](/Users/lanser/Code/Claw_news/spec/task003/contract.md)
2. 设计文档
   - [docs/tasks/task003/design.md](/Users/lanser/Code/Claw_news/docs/tasks/task003/design.md)
3. 设计审查结论
   - [docs/tasks/task003/design-review.md](/Users/lanser/Code/Claw_news/docs/tasks/task003/design-review.md)
4. 一页清单
   - [docs/tasks/task003/one-page.md](/Users/lanser/Code/Claw_news/docs/tasks/task003/one-page.md)
5. 实施计划
   - [docs/tasks/task003/plan.md](/Users/lanser/Code/Claw_news/docs/tasks/task003/plan.md)

开发顺序要求：

1. 先确认 `spec`
2. 再确认设计文档
3. 再确认设计审查结论
4. 最后按实施计划分任务开发

---

## 5. 开发主路径

新服务主路径固定为：

1. `app/config.py`
2. `app/tools/crawler.py`
3. `app/tools/llm.py`
4. `app/tools/wecom.py`
5. `app/agents/news_agent.py`
6. `app/scheduler/jobs.py`
7. `app/main.py`

旧 CLI `main.py` 保留，但不作为新服务内核。

---

## 6. 评审检查点

### 阻塞项

1. 是否固定内部 scheduler 为本轮主部署模式
2. 是否固定 `news_agent.run_once()` 为唯一任务内核
3. 是否固定单活部署约束

### 功能项

1. 是否每次抓取候选 `10` 条
2. 是否最终展示 `5` 条
3. 是否每条标题都带原文跳转链接
4. 是否复用原项目 RSS 评分逻辑
5. 是否支持 OpenAI-compatible LLM 配置

### 部署项

1. 是否支持 Docker 部署
2. 是否有 `/health`
3. 是否有 `POST /run/news`
4. 是否写清楚内部 scheduler 与外部 HTTP 调度的关系

### 文档项

1. `README.md` 是否同步更新
2. `.env.example` 是否同步更新
3. `deploy.example.sh` 是否同步更新

---

## 7. 最终一句话

本轮不是推翻旧项目，而是在同一仓库内新增一个“服务器常驻服务 + 定时任务 + 手动 HTTP 触发”的轻量 AI 助手入口，并复用原项目的 RSS 排序能力，最终每次从候选 `10` 条中筛出 `5` 条，用带原文链接的中文摘要推送到企业微信群。
