# Claw_news

每日自动收集 AI、工具、游戏和数码热点，经筛选和摘要后推送到已配置的消息渠道。

文档入口见 [`docs/README.md`](docs/README.md)。当前架构、选材策略、部署和排障说明均以 `docs/` 下的中文正式文档为准。

## 数据源

| 分类 | 源 | 方式 | 地区 |
|------|-----|------|------|
| 🤖 AI | HuggingFace Daily Papers | API | 国外 |
| 🤖 AI | 量子位 | RSS | 国内 |
| 🎮 游戏 | TapTap 下载榜 | 爬虫 | 国内 |
| 🎮 游戏 | 游研社 | RSS | 国内 |
| 📱 数码 | IT之家 | RSS | 国内 |
| 📱 数码 | 少数派 | RSS | 国内 |

## 选材规则

每次摘要目标为 10 条，先满足 AI、工具、游戏的最低数量，再按新鲜度、来源质量和来源多样性竞争。今日候选不足时，会从保留期内的历史候选补位。详细规则见 [内容选材](docs/架构/内容选材.md)。

## 快速开始

正式运行路径是 **FastAPI + APScheduler 服务模式**。旧 CLI 入口仍保留为兼容/本地辅助入口，但不再是生产发布主路径。

```bash
# 1. 一键安装
make install

# 2. 准备服务配置
cp .env.example .env
# 编辑 .env，填写三个 LLM_* 变量；需要实际推送时再配置至少一个渠道

# 3. 验证
make test
make dry-run

# 4. 启动正式服务
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

> **注意：**
> - 程序启动时会自动读取项目根目录 `.env`；进程环境中显式设置的变量优先级更高。请勿将包含真实密钥的 `.env` 提交到仓库。
> - `make dry-run` 只验证 CLI 兼容壳可启动，不触发 LLM 摘要或企业微信推送，也不要求 LLM / webhook 配置。
> - `make clean` 不删除 `data/`（运行状态），`make clean-data` 清空。
> - **不要直接使用系统 Python 跑 `pytest`**。标准入口是 `make install` 后再 `make test`。
> - `deploy.example.sh` 是公开部署参考模板；真实服务器地址和发布脚本只保留在本地运维环境。

### CLI 兼容入口

`main.py` 仍保留 `--period` 和 `--dry-run` 参数，主要用于旧脚本兼容。真实发布建议使用服务模式；CLI 与服务模式都读取项目根目录 `.env`，进程环境变量可覆盖其中配置。

## 定时自动运行（macOS launchd）

launchd 只适合本地或旧 CLI 兼容入口。生产服务使用 APScheduler 时不要同时加载 launchd，避免重复推送。

```bash
# 从模板复制后，按你的本机路径修改
cp docs/运维/launchd/com.lanser.clawnews.morning.plist.example ~/Library/LaunchAgents/com.lanser.clawnews.morning.plist
cp docs/运维/launchd/com.lanser.clawnews.evening.plist.example ~/Library/LaunchAgents/com.lanser.clawnews.evening.plist
# 将 {{PROJECT_DIR}} 替换为你的项目绝对路径

launchctl load ~/Library/LaunchAgents/com.lanser.clawnews.morning.plist
launchctl load ~/Library/LaunchAgents/com.lanser.clawnews.evening.plist

# 兼容 CLI：每天 9:00 早报 / 21:00 晚报
```

launchd 不会读取交互式 shell 的变量；程序会自动读取项目根目录 `.env`。安装后确认 `.env` 存在且权限为 `600`，再执行配置检查：

```bash
chmod 600 .env
make check-config
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

Claw_news 的正式发布路径是一个长运行的 FastAPI + APScheduler 服务：高频采集候选池，定时执行结构化 LLM 摘要，并向已配置的消息渠道推送摘要。

### 环境变量

服务模式统一使用项目根目录 `.env`。先复制 `.env.example` 到 `.env`，再填写实际值；进程环境变量可以覆盖 `.env` 中的同名字段：

```bash
cp .env.example .env
```

| Variable | Required | Description |
|----------|----------|-------------|
| `LLM_API_KEY` | Yes | API key for OpenAI-compatible LLM |
| `LLM_BASE_URL` | Yes | Base URL for LLM API |
| `LLM_MODEL` | Yes | Model name to use |
| `WECOM_WEBHOOK_URL` | Optional channel | WeCom bot webhook URL |
| `FEISHU_APP_ID` | Paired | Optional Feishu app ID; must be set with `FEISHU_APP_SECRET` and `FEISHU_CHAT_ID` |
| `FEISHU_APP_SECRET` | Paired | Optional Feishu app secret |
| `FEISHU_CHAT_ID` | Paired | Optional Feishu destination |
| `TELEGRAM_BOT_TOKEN` | Paired | Optional Telegram bot token; must be set together with `TELEGRAM_CHAT_ID` |
| `TELEGRAM_CHAT_ID` | Paired | Optional Telegram destination chat ID; must be set together with `TELEGRAM_BOT_TOKEN` |
| `TZ` | No | Timezone (default: `Asia/Shanghai`) |
| `NEWS_RSS_URLS` | Legacy | Historical URL-only RSS config; formal AI ingest uses `AI_RSS_*` below |
| `HF_PROXY` | No | HuggingFace collector proxy URL, mainly for restricted network environments |
| `HF_OPTIONAL` | No | `1` means HuggingFace failures are recorded as skipped instead of failed |
| `AI_RSS_MODE` | No | `append` (default) keeps built-ins; `replace` uses only `AI_RSS_FEEDS` |
| `AI_RSS_FEEDS` | No | Comma-separated `source|url` AI RSS feeds, e.g. `openai_blog|https://openai.com/news/rss.xml` |
| `PIP_INDEX_URL` | Build only | Optional primary PyPI index for `docker compose build`, useful on slow overseas links |
| `PIP_EXTRA_INDEX_URL` | Build only | Optional fallback PyPI index for `docker compose build` |

### HTTP 接口

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Service status and description |
| `GET` | `/health` | Health check plus latest ingest status |
| `POST` | `/run/news` | Manually trigger one publish cycle from the ingestion store |

### Docker 部署

```bash
# Optional: set a mirror first when the server reaches PyPI slowly
export PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
export PIP_EXTRA_INDEX_URL=https://pypi.org/simple

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

如果云服务器访问 GitHub 不稳定，不建议把服务器上的 `git pull` 作为主要部署路径。公开仓库只提供通用部署参考，不保存服务器地址、账号和私有发布脚本。

推荐顺序：

1. **首选：** 在本地维护私有发布脚本，用 `rsync` 同步代码到服务器
2. **进阶：** 由 GitHub Actions 构建并交付产物
3. **备选：** 在服务器上直接 `git pull`

完整部署指南：

- [docs/运维/部署.md](docs/运维/部署.md)

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
├── docs/                    # 中文项目文档；历史过程材料在 docs/归档/
└── data/                    # 运行时数据（gitignored）
```
