# 轻 OpenClaw 化 AI 助手服务设计文档

## 1. 文档目的

本文档用于指导 `Claw_news` 在当前仓库内新增一个服务化 MVP。

目标不是重写现有 CLI，而是在同一仓库内新增一个可部署到 Linux 服务器的长驻服务，用于：

1. 抓取 RSS 新闻
2. 调用 OpenAI-compatible LLM 生成中文摘要
3. 通过企业微信群机器人推送摘要
4. 提供 HTTP 手动触发入口
5. 提供定时调度能力

本文档只定义设计、边界、风险和审核要求，不包含代码实现。

---

## 2. 设计结论

### 2.1 总体方案

采用“同仓双入口”：

1. 保留现有 CLI 入口 `main.py`
2. 新增服务入口 `app/main.py`
3. 新服务优先复用现有领域对象、采集器和容错经验
4. 明确隔离 CLI 语义与服务语义，避免在仓库内长出两套业务逻辑

### 2.2 为什么不拆新仓

当前仓库已经具备以下稳定资产：

1. `HotItem` 数据模型与分类约束
2. RSS / HuggingFace / TapTap 采集经验
3. 企业微信推送实现与测试
4. 本地状态持久化与原子写入
5. `pytest + ruff + CI` 的基础工程化能力

如果另起新仓，会重复建设抓取、推送、去重、测试和部署约束，成本更高，后续迁移也更难。

### 2.3 为什么不能直接复用现有 `main.py`

当前 `main.py` 是一次性批处理脚本入口，而不是长驻服务内核。它直接承担了：

1. 进程退出语义 `sys.exit()`
2. 文件锁
3. 本地状态落盘
4. 批处理日志初始化
5. 推送后目录清理

这些行为适合 CLI，不适合 HTTP 请求和 APScheduler 常驻进程。

因此必须拆出服务内核，CLI、API、scheduler 只做薄入口。

### 2.4 关于“部署方式会不会变化”的结论

会变化，但不是必须“一步到位全量替换”。

当前项目本质上已经是“部署在服务器上定时触发”，只是触发方式偏脚本化：

1. 外部调度器触发
   - 例如 `launchd`、`cron`、系统任务
2. 启动一次 Python 进程
3. 执行 `main.py`
4. 推送完成后进程退出

新方案会把它改成“服务化常驻进程 + 内部 scheduler”：

1. 启动一个常驻服务进程
2. 服务对外提供 HTTP 接口
3. 服务内部使用 `APScheduler` 定时执行
4. 也允许外部通过 `POST /run/news` 手动触发

结论：

1. **部署目标仍然是服务器定时推送**
2. **变化的是触发与运行形态**
3. **不是从“定时任务”变成“非定时任务”，而是从“外部调脚本”变成“内部调服务任务”**

---

## 2.5 推荐部署策略

本轮给出两种部署策略，但只推荐其中一种作为正式交付。

### 方案 A：保留旧部署思路，改成“服务器外部定时调用 HTTP”

方式：

1. 部署 FastAPI 服务
2. 不启用或不依赖服务内 APScheduler
3. 继续使用服务器上的 `cron` / `systemd timer` / 平台定时器
4. 定时执行：

```bash
curl -X POST http://127.0.0.1:8000/run/news
```

优点：

1. 迁移心智成本最低
2. 和你现在“服务器定时触发”的模式最接近
3. 调度职责清晰，服务只负责执行

缺点：

1. 需要同时维护服务和外部定时器
2. 调度状态分散在服务外
3. 与 `new_design.md` 的 `APScheduler` 目标不完全一致

### 方案 B：服务内自带 APScheduler，容器启动后自动调度

方式：

1. 部署 FastAPI 服务
2. 服务启动时初始化 APScheduler
3. 在服务内注册 `09:00`、`14:00`、`20:00`
4. 外部只负责保活容器，不再负责定时触发

优点：

1. 更符合本轮 MVP 目标
2. 触发逻辑集中在应用内
3. HTTP 手动触发和定时触发共享同一任务内核

缺点：

1. 对单活部署要求更高
2. 不能随意开多 worker / 多副本
3. 需要明确 scheduler 生命周期和锁语义

### 本轮推荐

推荐 **方案 B 作为正式设计**，原因：

1. 与 `new_design.md` 一致
2. 开发与测试闭环更完整
3. 能同时保留 `/run/news` 作为手动触发入口

但要在文档中明确：

1. **这不是唯一可运行方案**
2. **如果生产环境更偏好外部调度，后续可以切回方案 A**
3. **业务内核必须设计成既能被 APScheduler 调用，也能被 HTTP 路由调用**

---

## 3. 设计原则

1. MVP 优先，只支持 RSS -> LLM -> WeCom 主链路
2. 复用优先，尽量复用已有领域模型和 collector 经验
3. 入口隔离，CLI/HTTP/Scheduler 不直接共享退出语义
4. 单活优先，本轮默认单实例调度，不设计多副本并发运行
5. 配置显式，LLM 采用 OpenAI-compatible 语义，不绑定单一供应商
6. 可审核，设计必须能映射到明确的测试点与评审清单

---

## 4. 当前仓库事实

### 4.1 适合复用的现有资产

高价值复用：

1. `collectors/base.py`
   - `HotItem`
   - `Category`
2. `aggregator/merger.py`
   - `Merger`
   - `compute_source_score`
   - `position_score`
3. `collectors/rss_sources.py`
   - 多 feed 配置
   - RSS 解析到结构化对象
4. `collectors/utils.py`
   - `safe_collect()` 的容错模式
5. `infra/storage/state_store.py`
   - 文件状态持久化
   - 原子写入

### 4.2 必须隔离的现有边界

不建议直接复用：

1. `main.py`
   - 含 `sys.exit()`、文件锁、批处理日志、清理逻辑
2. `run_push_sequence()`
   - 把 category 推送、状态提交和失败语义耦在一起
3. `pusher/wecom.py`
   - 现有实现是 CLI 热点展示导向的 markdown 推送器
4. `cleanup_old_digests()`
   - 这是离线 housekeeping，不应进入服务主链路

### 4.3 当前架构风险

P0 风险：

1. 脚本式入口与长驻服务进程模型冲突
2. 定时触发与手动触发共用状态时存在幂等性风险
3. APScheduler 挂到 FastAPI 启动时存在多 worker 重复调度风险
4. 新服务如果平移复制现有逻辑，会在同仓形成第二套流水线

P1 风险：

1. `feedparser.parse()` 当前是同步调用，服务化后会阻塞事件循环
2. 容器重启后若没有卷挂载，去重状态会丢失
3. 时区尚未建模，当前代码散落使用本地时间

---

## 5. 目标架构

### 5.1 逻辑分层

```text
HTTP / Scheduler / CLI
        |
        v
app/agents/news_agent.py
        |
        v
app/services/
  - crawl_service
  - summarize_service
  - notify_service
        |
        v
app/tools/
  - crawler.py
  - llm.py
  - wecom.py
        |
        v
现有 collectors/ infra/ 的可复用模块
```

### 5.2 目录设计

```text
app/
├── main.py
├── config.py
├── agents/
│   └── news_agent.py
├── tools/
│   ├── crawler.py
│   ├── llm.py
│   └── wecom.py
└── scheduler/
    └── jobs.py
```

说明：

1. `app/main.py` 只负责 FastAPI 生命周期、路由和 scheduler 挂载
2. `app/config.py` 只负责新服务配置，不侵入旧 `Settings`
3. `news_agent.py` 负责串联任务，不直接写路由
4. `crawler.py`、`llm.py`、`wecom.py` 分别负责外部系统调用
5. `jobs.py` 只负责调度注册，不内嵌业务逻辑

---

## 6. 核心流程设计

### 6.1 手动触发流程

```text
POST /run/news
  -> app.main 调用 news_agent.run_once()
  -> crawler 抓取 RSS
  -> 去重并裁剪到 10 条
  -> llm.summarize_news(items)
  -> wecom.send_text(summary)
  -> 返回结构化执行结果
```

### 6.2 定时流程

```text
APScheduler cron
  -> jobs.py 调度 news_agent.run_once()
  -> 执行链路与手动触发完全一致
  -> 共享同一把运行锁
```

### 6.3 失败流程

```text
任一阶段失败
  -> 记录错误日志
  -> 构造错误摘要
  -> 若 WECOM_WEBHOOK_URL 可用，则推送错误摘要
  -> 返回失败结果，不允许静默吞掉全链路异常
```

---

## 7. 配置设计

### 7.1 环境变量

新服务只读取环境变量：

1. `LLM_API_KEY`
2. `LLM_BASE_URL`
3. `LLM_MODEL`
4. `WECOM_WEBHOOK_URL`
5. `TZ`
6. `NEWS_RSS_URLS`

### 7.2 LLM 配置语义

LLM 不绑定 OpenAI 官方。

兼容目标定义为：

1. 支持 `base_url + api_key + model`
2. 调用协议兼容 OpenAI 风格 HTTP API
3. 切换供应商时只改配置，不改代码

### 7.3 配置兼容边界

1. 旧 CLI 继续使用 `config.yaml` + `PUSHER_WECOM_WEBHOOK`
2. 新服务不直接复用旧 `Settings`
3. 不做新旧配置合并，避免本轮引入迁移复杂度

---

## 8. 数据模型设计

### 8.1 服务内新闻项

服务侧统一新闻项结构：

```python
NewsItem = {
    "title": str,
    "link": str,
    "summary": str,
    "published_at": str,
}
```

### 8.2 与现有模型关系

实现上允许两种策略：

1. 直接使用现有 `HotItem` 作为中间对象
2. 在 `app/tools/crawler.py` 中将 `HotItem` 适配为轻量 `NewsItem`

推荐做法：

1. 采集层内部可复用 `HotItem`
2. `llm.py` 的输入使用轻量结构，减少对旧评分字段的依赖

---

## 9. 组件设计

### 9.1 `app/config.py`

职责：

1. 读取和校验新服务所需环境变量
2. 提供默认时区
3. 解析 `NEWS_RSS_URLS`

约束：

1. 不读取 `config.yaml`
2. 不引用现有 `Settings`

### 9.2 `app/tools/crawler.py`

职责：

1. 解析 RSS 源配置
2. 抓取多源 RSS
3. 清洗标题/摘要
4. 去重
5. 裁剪到 10 条

推荐复用：

1. `collectors/rss_sources.py` 的 feed 配置模式
2. HTML 清洗逻辑
3. `safe_collect()` 的容错思路

注意：

1. 若复用 `feedparser.parse()`，需迁移到线程池，避免阻塞事件循环

### 9.3 `app/tools/llm.py`

职责：

1. 封装 `summarize_news(items)` 调用
2. 输出中文摘要
3. 在无新闻时返回可推送结果
4. 在返回格式异常时抛出明确错误

输出格式固定为：

```text
今日 AI 新闻摘要
1. 标题
   - 核心内容
   - 重要性
   - 趋势判断

今日一句话判断
```

### 9.4 `app/tools/wecom.py`

职责：

1. 发送 text 消息
2. 检测单条过长
3. 进行截断或分段
4. 识别网络异常 / HTTP 异常 / 业务异常

设计决策：

1. 新服务使用 text，而不是复用当前热点 markdown 模板
2. 原因是 LLM 输出为长文本，text 更稳定，格式约束更少

### 9.5 `app/agents/news_agent.py`

职责：

1. 编排抓取
2. 编排 LLM 总结
3. 编排企微推送
4. 输出结构化结果
5. 统一错误处理

推荐返回结构：

```python
{
    "status": "ok" | "failed" | "skipped",
    "fetched_count": int,
    "pushed": bool,
    "summary_preview": str,
    "errors": list[str],
}
```

### 9.6 `app/scheduler/jobs.py`

职责：

1. 注册 `09:00`、`14:00`、`20:00`
2. 绑定统一时区
3. 启动与关闭 scheduler

关键约束：

1. 本轮默认单进程单实例部署
2. 不支持多 worker 并行启动 scheduler

### 9.7 `app/main.py`

职责：

1. 初始化 FastAPI
2. 生命周期中挂载 scheduler
3. 提供：
   - `GET /`
   - `GET /health`
   - `POST /run/news`

约束：

1. 路由层不直接处理爬取、总结和推送细节
2. 路由层不允许出现 `sys.exit()`

---

## 10. 状态与幂等设计

### 10.1 本轮设计

本轮采用单活策略：

1. 单容器
2. 单 `uvicorn` worker
3. API 触发与 scheduler 触发共用同一把运行锁

### 10.2 为什么不做多实例

当前仓库的状态存储是本地 JSON 文件，不适合多实例并发写入。

因此本轮不做：

1. 多副本调度
2. 分布式锁
3. 数据库存储

### 10.3 锁设计要求

开发时必须满足：

1. 任务运行中再次触发，返回“已有任务执行中”
2. API 和 scheduler 使用相同锁语义
3. 锁失败不视为系统异常，而视为可解释状态

---

## 11. 部署设计

### 11.1 容器模型

默认部署模型：

1. 一个容器
2. 一个 API 进程
3. 进程内部带 scheduler

这是本轮**推荐部署模型**，不是唯一可能的运行方式。

### 11.1.1 与旧部署方式的关系

旧方式：

1. 服务器部署 Python 环境
2. 外部调度器定时执行 `python main.py --period ...`
3. 进程执行完退出

新方式：

1. 服务器部署一个常驻 FastAPI 容器或进程
2. 服务内部使用 APScheduler 定时执行
3. 进程不退出，持续对外提供 `/health` 与 `/run/news`

不会变化的部分：

1. 仍然是服务器部署
2. 仍然是定时自动推送
3. 仍然可以保留人工手动触发能力

发生变化的部分：

1. 从“一次性脚本进程”变成“常驻服务进程”
2. 从“外部调度脚本”变成“内部调度任务”
3. 部署关注点从 Python 运行脚本变成服务保活、健康检查和容器配置

### 11.1.2 迁移建议

建议按两阶段迁移，而不是一次替换到底：

阶段 1：

1. 先把服务跑起来
2. 先验证 `/health` 和 `POST /run/news`
3. 生产上可以暂时继续用服务器外部定时器调用 HTTP

阶段 2：

1. 再启用 APScheduler
2. 再收口为单活服务内调度
3. 最终移除旧脚本调度链路

这样做的好处：

1. 便于排查问题
2. 降低“服务上线 + 调度切换”同时发生的风险
3. 不影响当前已有服务器定时推送习惯

### 11.2 部署约束

1. `docker-compose.yml` 必须挂载 `.env`
2. 如果复用本地状态文件，必须挂载 `data/`
3. 不允许多 worker 启动
4. 若启用服务内 APScheduler，则不允许多副本同时运行
5. 若暂时采用服务器外部调度，则应关闭或禁用内部 scheduler，避免双重触发

推荐命令：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

不推荐：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
```

---

## 12. 测试设计

### 12.1 单元测试

至少覆盖：

1. `config.py` 环境变量解析
2. `crawler.py` 去重与截断
3. `crawler.py` RSS 源失败容错
4. `llm.py` 正常摘要
5. `llm.py` 空新闻摘要
6. `wecom.py` 超长消息截断 / 分段
7. `wecom.py` HTTP / 业务错误
8. `news_agent.py` 成功与失败路径

### 12.2 集成测试

至少覆盖：

1. `GET /health`
2. `GET /`
3. `POST /run/news`
4. 同时触发两个任务时的锁语义
5. scheduler 只注册一次

### 12.3 部署冒烟

至少覆盖：

1. `docker compose config`
2. 容器能启动
3. `/health` 返回 200
4. 若启用内部 scheduler，确认只注册一次任务
5. 若采用外部 HTTP 调度方案，确认 `POST /run/news` 可被无状态重复调用且锁语义正确

---

## 13. Agent 协作设计

本项目建议使用多 agent 但保持职责清晰。

### 13.1 角色划分

1. Architect Agent
   - 维护 spec、设计文档、实施计划
   - 负责边界决策和最终审核

2. Worker Agent A
   - 负责 `app/config.py`、`app/tools/llm.py`

3. Worker Agent B
   - 负责 `app/tools/crawler.py`、`app/agents/news_agent.py`

4. Worker Agent C
   - 负责 `app/tools/wecom.py`、`app/scheduler/jobs.py`、`app/main.py`

5. Spec Review Agent
   - 按 `spec/task003/contract.md` 审核是否越界

6. Quality Review Agent
   - 审核代码质量、测试完整性、文档一致性

### 13.2 协作原则

1. 每个 Worker 只改自己的文件集合
2. 任何实现前先对照 `spec/task003/contract.md`
3. 每个任务完成后先过 Spec Review，再过 Quality Review
4. 不允许在 review 阶段引入范围外需求

---

## 14. 审核准则

### 14.1 设计审核

必须确认：

1. 新服务没有直接复用 `main.py` 的退出语义
2. LLM 是 OpenAI-compatible，而不是硬编码 OpenAI 官方
3. API 和 scheduler 共享同一任务内核
4. text 推送与超长处理策略明确
5. 旧 CLI 仍可用

### 14.2 实现审核

必须阻断：

1. 在 `app/` 中复制出第二套 RSS 解析核心逻辑，但不复用现有 collector 经验
2. 在业务层调用 `sys.exit()`
3. 默认启用多 worker 调度
4. 忽略锁冲突与状态持久化
5. 只改代码不改 README / `.env.example` / Docker 文件
6. 没有写清楚采用“内部 scheduler”还是“外部 HTTP 调度”的部署模式
7. 同时启用外部定时器和内部 scheduler，却没有防重复策略

---

## 15. 非本轮范围

1. 微信回调
2. 聊天输入
3. 浏览器自动化
4. 数据库
5. 向量库
6. 多模型自动切换
7. 多 key 预算调度
8. 多副本高可用调度

---

## 16. 结论

这次改造最关键的不是引入 FastAPI 或 APScheduler，而是：

1. 在同仓中新增服务入口
2. 提炼可复用的服务内核
3. 明确隔离现有 CLI 语义
4. 在单活部署前提下完成一个稳定 MVP

只要开发阶段严格遵守上述边界，这个方案可以低风险落地，并为后续扩展更多 source、更多模型供应商和更强的 agent 能力留下空间。
