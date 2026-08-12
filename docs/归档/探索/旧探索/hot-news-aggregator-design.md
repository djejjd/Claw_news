# 每日热点信息聚合与推送工具 设计文档

## 1. 项目概述

定时（每日）从多个信息源获取 AI、游戏、数码设备三个方向的热点信息，合并排序后通过企业微信 Bot 推送到用户手机。

## 2. 数据源

### AI 方向
| 来源 | 方式 | 说明 |
|------|------|------|
| Hugging Face Daily Papers | API（免费） | 社区投票排序，每日 AI 论文精选 |
| 机器之心 / 量子位 | RSS | AI 行业前沿资讯 |

### 游戏方向
| 来源 | 方式 | 说明 |
|------|------|------|
| TapTap 热门榜 | 轻量爬虫（httpx + BS4） | Top 10 游戏热度 |
| 游研社 / 机核 | RSS | 游戏深度内容和资讯 |

### 数码设备方向
| 来源 | 方式 | 说明 |
|------|------|------|
| IT之家 热榜 | 轻量爬虫（httpx + BS4） | 数码硬件和科技热点 |
| 少数派 | RSS | 工具、设备、应用体验 |

RSS/API 优先，仅 TapTap 和 IT之家需爬虫兜底。

## 3. 架构设计

三层结构：

```
采集层 (collectors/)       聚合层 (aggregator/)       推送层 (pusher/)
───────────────────       ──────────────────        ──────────────────
huggingface.py ───────→   ┌──────────────┐
rss_sources.py ───────→   │  Merger      │        ┌──────────────┐
taptap.py ────────────→   │  + Dedup     │ ──────→│  Formatter   │──→ 企业微信 Bot
ithome.py ────────────→   │  + Rank      │        │  + Sender    │
                          └──────────────┘        └──────────────┘
```

- **采集层**：每个源一个模块，输出统一格式 `HotItem(name, url, summary, source, category, score)`
- **聚合层**：按分类合并所有条目 → URL 去重 → 综合得分排序 → 每方向取 Top 5
- **推送层**：格式化为 Markdown 消息，分三条发送（每方向一条）

## 4. 排序算法

综合得分 = 来源热度分（0-10，归一化）+ 时间衰减分

- **来源热度分**：源自带排名/票数/阅读量映射至 0-10；无热度数据的 RSS 源默认 5
- **时间衰减**：24 小时内新文章加分，超过 24 小时每 12 小时衰减 1 分

同一分类下全量竞争排序，取 Top 5。

## 5. 推送格式

企业微信 Markdown 消息，每方向一条：

```
🤖 AI 热点 | 05/15
━━━━━━━━━━━━━━━━━━━
1. [标题](链接)
   一句话摘要

2. [标题](链接)
   一句话摘要
━━━━━━━━━━━━━━━━━━━
```

- 每方向 5 条，标题可点击跳转原文
- 三条消息分开发送，避免单条超长
- 摘要来源：自有简介直接使用，无简介的由合并逻辑生成简短描述

## 6. 定时调度

Mac 本地 `launchd`，每日早 9 点触发 `python main.py`。也可手动执行。

## 7. 技术栈

- Python 3.10+
- `httpx` + `BeautifulSoup4` — 轻量爬虫（静态页面，无需 Playwright）
- `feedparser` — RSS 解析
- `pyyaml` — 配置管理
- `launchd` (plist) — 定时调度

## 8. 项目结构

```
Claw_news/
├── main.py              # 入口 + 调度
├── config.yaml           # 源开关、推送配置
├── collectors/
│   ├── base.py           # 数据模型 HotItem
│   ├── huggingface.py    # API
│   ├── rss_sources.py    # RSS 多源
│   ├── taptap.py         # 爬虫
│   └── ithome.py         # 爬虫
├── aggregator/
│   └── merger.py         # 合并、去重、排序
├── pusher/
│   └── wecom.py          # 企业微信 Bot 推送
├── data/                 # 历史记录
└── requirements.txt
```

## 9. 配置项

```yaml
collectors:
  sources:
    huggingface: true
    rss: true
    taptap: true
    ithome: true
  top_n: 5

pusher:
  wecom_webhook: ""  # 企业微信 Bot Webhook URL

schedule:
  time: "09:00"
```
