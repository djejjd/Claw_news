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

```bash
# 1. 一键安装
make install

# 2. 配置 webhook
#    首先必须有 config.yaml（从模板复制）:
cp config.example.yaml config.yaml
#    然后配置 webhook（二选一）:
#    方式 A: 环境变量（推荐，覆盖 YAML 中的 webhook）
export PUSHER_WECOM_WEBHOOK="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY_HERE"
#    方式 B: 直接在 config.yaml 中填写 webhook

# 3. 验证
make test
make dry-run

# 4. 推送
make run-morning
```

> **注意：**
> - `.env.example` 是人工参考模板，程序不会自动加载。如需环境变量注入，请在 shell / launchd / cron 中 `export`。
> - `--dry-run` 不要求 webhook 配置。
> - `make clean` 不删除 `data/`（运行状态），`make clean-data` 清空。
> - **不要直接使用系统 Python 跑 `pytest`**。标准入口是 `make install` 后再 `make test`。
> - `deploy.example.sh` 是部署参考模板，只做安装+dry-run 验证，不是生产推送入口。

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

## Service Mode

Claw_news also provides a long-running service mode with FastAPI + APScheduler for automated RSS news collection, OpenAI-compatible LLM summarization, and WeCom bot text push.

### Environment Variables

The service mode reads configuration from environment variables. Copy `.env.example` to `.env` and fill in your values:

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
| `NEWS_RSS_URLS` | Yes | Comma-separated RSS feed URLs, e.g. `https://www.qbitai.com/feed,https://sspai.com/feed` |

### HTTP Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Service status and description |
| `GET` | `/health` | Health check |
| `POST` | `/run/news` | Manually trigger a news collection + summarization + push cycle |

### Docker Deployment

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

### Recommended Delivery Strategy

For cloud servers where access to GitHub may be unstable, do not treat `git pull` on the server as the primary deployment path.

Recommended order:

1. **Preferred:** sync code from a local machine or CI to the server with `scp` or `rsync`
2. **Advanced:** let GitHub Actions build and deliver artifacts to the server
3. **Fallback only:** direct `git pull` on the server

See the full deployment guide:

- [docs/operations/deploy/server-guide.md](docs/operations/deploy/server-guide.md)

### Deployment Modes

**Mode A: Internal APScheduler (recommended)**

The service schedules its own cron jobs at 09:00, 14:00, and 20:00. The container keeps a single process running with a built-in scheduler. This is the default mode.

**Mode B: External HTTP trigger**

Disable the internal scheduler and use an external timer (cron, systemd timer, etc.) to call `POST /run/news`. This is available as a migration-friendly option if you prefer to keep your existing scheduling infrastructure.

> **Important:** This is a single-instance service. Do not run multiple replicas or workers, as deduplication state is stored in local files.

### LLM Provider Compatibility

The service uses an OpenAI-compatible HTTP interface. Any provider that supports `base_url + api_key + model` works — just change the three `LLM_*` environment variables. Examples: OpenAI, DeepSeek, Qwen (通义千问), Groq, local vLLM, Ollama.

### Local Development (without Docker)

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
├── main.py                  # 旧 CLI 入口：--period morning|evening [--dry-run]
├── config.example.yaml      # 旧 CLI 配置模板
├── pyproject.toml           # 项目元数据与依赖
├── Makefile                 # 统一命令入口
├── .env.example             # 环境变量模板（CLI + Service）
├── requirements.txt         # 运行时依赖参考
├── Dockerfile               # Docker 镜像
├── docker-compose.yml       # Docker 服务编排
├── deploy.example.sh        # 部署参考模板
├── app/                     # 新 AI 助手服务入口
│   ├── main.py              # FastAPI 入口 + lifespan
│   ├── config.py            # env 配置（AppConfig）
│   ├── agents/
│   │   └── news_agent.py    # 任务编排内核
│   ├── tools/
│   │   ├── crawler.py       # RSS 抓取与去重
│   │   ├── llm.py           # OpenAI-compatible LLM 摘要
│   │   └── wecom.py         # 企业微信 text 推送
│   └── scheduler/
│       └── jobs.py          # APScheduler 09:00/14:00/20:00
├── collectors/
│   ├── base.py              # HotItem 数据模型 + time_modifier
│   ├── rss_sources.py       # RSS 多源采集
│   ├── huggingface.py       # HuggingFace Daily Papers
│   ├── taptap.py            # TapTap 下载榜爬虫
│   └── utils.py             # safe_collect 公共辅助
├── aggregator/
│   └── merger.py            # 三维评分 + 关键词保底竞争
├── pusher/
│   └── wecom.py             # 旧 CLI 企业微信推送
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
