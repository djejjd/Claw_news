# Claw_news V2 Final 设计文档

## 1. 概述

每日早晚两次自动推送 AI/游戏/数码三大方向热点。多源采集 + 三维评分 + 关键词保底竞争。launchd 定时触发，无需手动运行。

## 2. 数据源

| 分类 | 源 | 方式 | 每次取 | 评分依据 |
|------|-----|------|--------|---------|
| 🤖 AI | HuggingFace Daily Papers | API | 10 条 | upvotes |
| 🤖 AI | 量子位 | RSS | 10 条 | position + keyword + time |
| 🎮 Game | TapTap 下载榜 | 爬虫 | 10 条 | 排名 |
| 🎮 Game | 游研社 | RSS | 10 条 | position + keyword + time |
| 📱 Device | IT之家 | RSS | 10 条 | position + keyword + time |
| 📱 Device | 少数派 | RSS | 10 条 | position + keyword + time |

## 3. 调度

```
launchd 自动触发，无需手动:

9:00  → python main.py --period morning   (早报)
21:00 → python main.py --period evening   (晚报)
```

## 4. 评分公式

### 4.1 source_score

```
source_score = position_score + keyword_bonus + time_modifier(period)

position_score:   RSS 排位 → 第1=10.0，线性递减至第10=5.5
keyword_bonus:    标题/摘要命中对应分类关键词 → +1.0
                  未命中 → 0
time_modifier:    早报: 今天+昨天→0,  更早→-2.0
                  晚报: 今天→0,  昨天→-1.0,  更早→-2.0
```

> HF/TapTap 使用自带的 upvotes/rank 评分，不受上述公式影响。

### 4.2 time_modifier 实现

```python
def time_modifier(pub_date: str, period: str = "morning") -> float:
    diff = (date.today() - date.fromisoformat(pub_date)).days
    if period == "morning":
        if diff <= 1: return 0      # today + yesterday
        return -2.0                 # older
    else:  # evening
        if diff == 0: return 0      # today
        if diff == 1: return -1.0   # yesterday
        return -2.0                 # older
```

### 4.3 关键词库

```yaml
keywords:
  ai: [AI, 大模型, GPT, LLM, 机器学习, 深度学习, 人工智能, 神经网络, 训练, Agent, 模型, 算法]
  game: [游戏, 手游, 主机, Steam, Switch, PS5, Xbox, 上线, 赛季, 联动, 版本, 新游, 评测, 发售]
  device: [芯片, 手机, 笔记本, 显卡, CPU, 处理器, iPhone, 系统, 发布, 评测, 新品, 上市, 小米, 华为, 苹果]
```

### 4.4 HotItem 新增字段

```python
keyword_hit: bool = False  # 是否命中分类关键词
pub_date: str = ""         # yyyy-mm-dd
```

## 5. 竞争规则

```
每个分类 20 条 = 源A 10条 + 源B 10条

Step 1 — 关键词保底（每源各 1 条）:
  源A 中筛选 keyword_hit=True → 取 source_score 最高 1 条
  源A 中无命中 → 取源A全部剩余中 source_score 最高 1 条
  源B 同理，共 2 条

Step 2 — 全量竞争:
  去除已选 2 条，剩余按 source_score 降序 → 取前 3 条

Step 3 — 最终排序:
  5 条按 source_score 降序展示
  每源至少 1 条，最多 4 条
```

## 6. 推送格式

```
🤖 AI 热点 | 05/16 早报
━━━━━━━━━━━━━━━━━━━
1. [续] [EN] [LLaMA 4 发布](https://...)
   Meta 发布最新开源大模型，性能超越...
   — HuggingFace

2. [新] [华为云 Agentic AI 新布局](https://...)
   华为云创想者大会主题论坛议程公布
   — 量子位
━━━━━━━━━━━━━━━━━━━
```

- `[EN]` — HuggingFace 英文论文
- `[续]` — 上一条推送出现过（比对 pushed_urls.json）
- `[新]` — 首次出现
- `— 来源名` — 条目末尾标注来源
- 摘要 HTML 已清理

## 7. 文件变更

| 文件 | 操作 | 说明 |
|------|------|------|
| `collectors/base.py` | 改 | + keyword_hit, pub_date, time_modifier |
| `config.yaml` | 改 | + keywords, 量子位替换机器之心, fetch_count=10 |
| `main.py` | 改 | --period morning/evening, 每次独立采集+评分+推送 |
| `collectors/rss_sources.py` | 改 | 机器之心→量子位, fetch_count=10, HTML去标签, keyword_hit, pub_date |
| `collectors/huggingface.py` | 改 | fetch_count=10, pub_date |
| `collectors/taptap.py` | 改 | fetch_count=10, pub_date |
| `aggregator/merger.py` | 改 | 三维评分 + 关键词保底竞争 |
| `pusher/wecom.py` | 改 | HTML去标签, [EN]/[续]/[新], 来源标注 |
| `data/pushed_urls.json` | 新建 | 记录上次推送 URL，判断 [续]/[新] |
| `~/Library/LaunchAgents/` | 新建 | morning + evening 两个 plist |

## 8. 配置

```yaml
collectors:
  fetch_count: 10
  sources:
    huggingface: true
    rss: true
    taptap: true

rss_feeds:
  - url: "https://www.qbitai.com/feed"
    category: "ai"
  - url: "https://sspai.com/feed"
    category: "device"
  - url: "https://www.ithome.com/rss/"
    category: "device"
  - url: "https://www.yystv.cn/rss/feed"
    category: "game"

keywords:
  ai:
    - AI|大模型|GPT|LLM|机器学习|深度学习|人工智能|神经网络|训练|Agent|模型|算法
  game:
    - 游戏|手游|主机|Steam|Switch|PS5|Xbox|上线|赛季|联动|版本|新游|评测|发售
  device:
    - 芯片|手机|笔记本|显卡|CPU|处理器|iPhone|系统|发布|评测|新品|上市|小米|华为|苹果

pusher:
  wecom_webhook: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=a1cd9e9d-3c2c-4948-aa2e-f61be9869b29"
```

## 9. 验收标准

1. `python main.py --period morning --dry-run` 输出早报格式
2. 每分类两源至少各 1 条
3. 早报当天+昨天不降权，晚报今天不降权
4. HTML 标签无残留，HF 条目标题含 `[EN]`
5. `pytest tests/` 全部通过
6. launchd 定时自动执行，无需手动
