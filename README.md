# Claw_news

每日早晚两次自动推送 AI / 游戏 / 数码三大方向热点到企业微信群。

## 数据源

| 分类 | 源 | 方式 | 地区 |
|------|-----|------|------|
| 🤖 AI | HuggingFace Daily Papers | API | 国外 |
| 🤖 AI | 量子位 | RSS | 国内 |
| 🎮 游戏 | TapTap 下载榜 | 爬虫 | 国内 |
| 🎮 游戏 | 游研社 | RSS | 国内 |
| 📱 数码 | IT之家 | RSS | 国内 |
| 📱 数码 | 少数派 | RSS | 国内 |

## 评分机制

每源取 10 条，每分类 2 源共 20 条竞争 5 个位置：

```
RSS 源评分 = position_score(#1=10.0 → #10=5.5) + keyword_bonus(+1.0) + time_modifier(period)
HF/TapTap = 自带 upvotes/排名分数

竞争规则:
  Step 1 — 关键词保底: 每源至少 1 条(优先选命中关键词的)
  Step 2 — 全量竞争: 剩余 3 条按分数自由竞争
```

时间修正：
- **早报**: 当天+昨天的新闻不降权，更早 -2.0
- **晚报**: 当天不降权，昨天 -1.0，更早 -2.0

## 快速开始

正式运行路径是 **FastAPI + APScheduler 服务模式**。旧 CLI 入口仍保留为兼容/本地辅助入口，但不再是生产发布主路径。

```bash
# 1. 一键安装
make install

# 2. 准备服务配置
cp .env.example .env
# 编辑 .env，填写 LLM_* 与 WECOM_WEBHOOK_URL

# 3. 验证
make test
make dry-run

# 4. 启动正式服务
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

> **注意：**
> - `.env.example` 是人工参考模板，程序不会自动加载。如需环境变量注入，请在 shell / launchd / cron 中 `export`。
> - `make dry-run` 只验证 CLI 兼容壳可启动，不触发 LLM 摘要或企业微信推送，也不要求 LLM / webhook 配置。
> - `make clean` 不删除 `data/`（运行状态），`make clean-data` 清空。
> - **不要直接使用系统 Python 跑 `pytest`**。标准入口是 `make install` 后再 `make test`。
> - `deploy.example.sh` 是部署参考模板，只做安装+dry-run 验证，不是生产推送入口。

### CLI 兼容入口

`main.py` 仍保留 `--period` 和 `--dry-run` 参数，主要用于旧脚本兼容。真实发布建议使用服务模式；如果必须使用 CLI 真实推送，需要提供与服务模式一致的 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL` 和 `WECOM_WEBHOOK_URL` 环境变量。

## 定时自动运行 (macOS launchd)

```bash
# 从模板复制后，按你的本机路径修改
cp docs/operations/launchd/com.lanser.clawnews.morning.plist.example ~/Library/LaunchAgents/com.lanser.clawnews.morning.plist
cp docs/operations/launchd/com.lanser.clawnews.evening.plist.example ~/Library/LaunchAgents/com.lanser.clawnews.evening.plist
# 将 {{PROJECT_DIR}} 替换为你的项目绝对路径

launchctl load ~/Library/LaunchAgents/com.lanser.clawnews.morning.plist
launchctl load ~/Library/LaunchAgents/com.lanser.clawnews.evening.plist

# 每天 9:00 早报 / 21:00 晚报，自动推送
```

## 推送格式

```
🤖 AI 热点 | 05/16 早报
━━━━━━━━━━━━━━━━━━━
1. [新] [华为云 Agentic AI 新布局](https://...)
   华为云创想者大会主题论坛议程公布
   — 量子位 · 国内

2. [EN] [新] [Long Context Pre-Training...](https://...)
   以极端序列长度训练因果变换器...
   — HuggingFace · 国外
━━━━━━━━━━━━━━━━━━━
```

- `[EN]` — HuggingFace 英文论文（摘要已翻译为中文）
- `[新]` — 本日首次出现
- `[续]` — 上次推送已出现过
- 来源名 + 国内/国外标注

## 服务模式

Claw_news 的正式发布路径是一个长运行的 FastAPI + APScheduler 服务：高频采集候选池，定时执行结构化 LLM 摘要，并向企业微信群推送一条 markdown 摘要。

### 环境变量

服务模式从环境变量读取配置。先复制 `.env.example` 到 `.env`，再填写实际值：

```bash
cp .env.example .env
```

| Variable | Required | Description |
|----------|----------|-------------|
| `LLM_API_KEY` | Yes | API key for OpenAI-compatible LLM |
| `LLM_BASE_URL` | Yes | Base URL for LLM API |
| `LLM_MODEL` | Yes | Model name to use |
| `WECOM_WEBHOOK_URL` | Yes | WeCom bot webhook URL |
| `TZ` | No | Timezone (default: `Asia/Shanghai`) |
| `NEWS_RSS_URLS` | Legacy | Historical URL-only RSS config; formal AI ingest uses `AI_RSS_*` below |
| `AI_RSS_MODE` | No | `append` (default) keeps built-ins; `replace` uses only `AI_RSS_FEEDS` |
| `AI_RSS_FEEDS` | No | Comma-separated `source|url` AI RSS feeds, e.g. `openai_blog|https://openai.com/news/rss.xml` |

### HTTP 接口

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Service status and description |
| `GET` | `/health` | Health check plus latest ingest status |
| `POST` | `/run/news` | Manually trigger one publish cycle from the ingestion store |

### Docker 部署

```bash
# Build and start the service
docker compose up -d --build

# Check health
curl http://127.0.0.1:8000/health

# Manually trigger a news run
curl -X POST http://127.0.0.1:8000/run/news

# View logs
docker compose logs -f
```

### 推荐交付策略

如果云服务器访问 GitHub 不稳定，不建议把服务器上的 `git pull` 作为主要部署路径。

推荐顺序：

1. **首选：** 从本地或 CI 用 `scp` / `rsync` 同步代码到服务器
2. **进阶：** 由 GitHub Actions 构建并交付产物
3. **备选：** 在服务器上直接 `git pull`

完整部署指南：

- [docs/operations/deploy/server-guide.md](docs/operations/deploy/server-guide.md)

### 部署模式

**模式 A：内部 APScheduler（推荐）**

服务内置一个 09:00 发布任务，以及一个每 30 分钟刷新候选池的高频采集任务。当存在最近的 GitHub 项目快照时，摘要可附加 3 条项目补充。容器内保持单进程运行，这是默认模式。

**模式 B：外部 HTTP 触发**

禁用内部 scheduler，并用外部计时器（cron、systemd timer 等）调用 `POST /run/news`。如果你希望保留现有调度基础设施，可以用这种迁移友好的模式。

> **重要：** 这是单实例服务。去重状态存储在本地文件中，不要运行多个副本或多个 worker。

### LLM Provider 兼容性

服务使用 OpenAI-compatible HTTP 接口。任何支持 `base_url + api_key + model` 的供应商都可接入，只需要修改三个 `LLM_*` 环境变量。例如 OpenAI、DeepSeek、Qwen（通义千问）、Groq、本地 vLLM、Ollama。

### 本地开发（不使用 Docker）

```bash
# Set up environment
cp .env.example .env
# Edit .env with your keys

# Install and run
make install
uvicorn app.main:app --host 0.0.0.0 --port 8000

# In another terminal
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/run/news
```

## License

MIT — see [LICENSE](LICENSE)

## 项目结构

```
Claw_news/
├── main.py                  # CLI 兼容壳，复用统一 pipeline
├── config.example.yaml      # 历史兼容配置模板
├── pyproject.toml           # 项目元数据与依赖
├── Makefile                 # 统一命令入口
├── .env.example             # 环境变量模板（CLI + Service）
├── requirements.txt         # 运行时依赖参考
├── Dockerfile               # Docker 镜像
├── docker-compose.yml       # Docker 服务编排
├── deploy.example.sh        # 部署参考模板
├── app/                     # 正式服务入口
│   ├── main.py              # FastAPI 入口 + lifespan
│   ├── config.py            # env 配置（AppConfig）
│   ├── agents/
│   │   └── news_agent.py    # 任务编排内核
│   ├── tools/
│   │   ├── crawler.py       # 历史兼容模块
│   │   ├── llm.py           # OpenAI-compatible LLM 摘要
│   │   └── wecom.py         # 历史兼容文本推送模块
│   └── scheduler/
│       └── jobs.py          # 09:00 发布 + 高频 ingest
├── collectors/
│   ├── base.py              # HotItem 数据模型 + time_modifier
│   ├── rss_sources.py       # RSS 多源采集
│   ├── huggingface.py       # HuggingFace Daily Papers
│   ├── taptap.py            # TapTap 下载榜爬虫
│   └── utils.py             # safe_collect 公共辅助
├── aggregator/
│   └── merger.py            # 三维评分 + 关键词保底竞争
├── pusher/
│   └── wecom.py             # WeCom markdown 推送适配
├── infra/
│   ├── config/
│   │   └── settings.py      # 旧 CLI 配置
│   └── storage/
│       └── state_store.py   # 原子化状态持久化
├── tests/                   # pytest 测试
├── .github/workflows/
│   └── ci.yml               # CI：install → lint → test
├── docs/                    # 设计文档 + launchd plist
└── data/                    # 运行时数据（gitignored）
```
