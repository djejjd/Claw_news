# Claw_news V2 Final 设计文档

## 1. 概述

每日早晚两次推送 AI/游戏/数码三大方向热点。多源采集 + 多维评分 + 关键词保底竞争。

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
每天 8 个时间点触发：

  --collect（仅采集 RSS + 存入 store）:
    0:00, 3:00, 6:00
    12:00, 15:00, 18:00

  --push（全量采集 + 合并 store + 评分 + 推送）:
    9:00  → 早报
    21:00 → 晚报
```

每次 `--collect` 把 RSS 条目追加到 `data/rss_store.json`。`--push` 时合并 store 中过去 24h 的条目去重，保证不遗漏。

## 4. 评分公式

### 4.1 source_score（RSS 条目）

```
source_score = position_score + keyword_bonus + time_modifier

position_score:  RSS 排位 → 第1=10.0，第10=5.5（线性递减）
keyword_bonus:   标题/摘要命中对应分类关键词 → +1.0
                未命中 → 0
time_modifier:   发布时间在今天       → 0
                发布时间在昨天       → -1.0
                发布时间在前天或更早  → -2.0
```

> HF/TapTap 使用自带的 upvotes/rank 评分，不受上述公式影响。

### 4.2 final_score

```
final_score = source_score + time_decay_bonus（时效衰减，同 V1）
```

### 4.3 关键词库

```yaml
keywords:
  ai: [AI, 大模型, GPT, LLM, 机器学习, 深度学习, 人工智能, 神经网络, 训练, Agent, 模型, 算法]
  game: [游戏, 手游, 主机, Steam, Switch, PS5, Xbox, 上线, 赛季, 联动, 版本, 新游, 评测, 发售]
  device: [芯片, 手机, 笔记本, 显卡, CPU, 处理器, iPhone, 系统, 发布, 评测, 新品, 上市, 小米, 华为, 苹果]
```

### 4.4 新增 HotItem 字段

```python
keyword_hit: bool = False  # 是否命中分类关键词
pub_date: str = ""         # 发布日期 yyyy-mm-dd，用于 time_modifier 计算
```

## 5. 竞争规则

```
每个分类 20 条 = 源A 10条 + 源B 10条

Step 1 — 关键词保底（每源各 1 条）:
  源A 中筛选 keyword_hit=True → 取 final_score 最高 1 条
  源A 中无命中 → 取源A全部剩余中 final_score 最高 1 条
  源B 同理
  共 2 条

Step 2 — 全量竞争:
  去除已选 2 条，剩余按 final_score 降序 → 取前 3 条

Step 3 — 最终排序:
  5 条按 final_score 降序展示
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

...
━━━━━━━━━━━━━━━━━━━
```

改进点：
- `[续]` — 上一条推送出现过（比对 pushed_urls.json）
- `[新]` — 首次出现
- HF 英文条目标题前加 `[EN]`
- 每条目补来源标注 `— 来源名`
- 摘要 HTML 标签已清理

## 7. 文件变更

| 文件 | 操作 | 说明 |
|------|------|------|
| `collectors/base.py` | 改 | + keyword_hit, pub_date 字段 |
| `config.yaml` | 改 | + keywords, 量子位替换机器之心, fetch_count=10 |
| `main.py` | 改 | + --collect / --push 模式, + store 读写 |
| `collectors/rss_sources.py` | 改 | 机器之心→量子位, fetch_count=10, HTML去标签, pub_date 提取 |
| `collectors/huggingface.py` | 改 | fetch_count=10 |
| `collectors/taptap.py` | 改 | fetch_count=10 |
| `aggregator/merger.py` | 改 | 多维评分 + 关键词保底竞争 |
| `pusher/wecom.py` | 改 | HTML去标签, [EN]/[续]/[新] 标记, 来源标注 |
| `data/pushed_urls.json` | 新建 | 记录最近推送的 URL，用于 [续]/[新] 判断 |

## 8. 配置项

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
    - AI
    - 大模型
    - GPT
    - LLM
    - 机器学习
    - 深度学习
    - 人工智能
    - 神经网络
    - 训练
    - Agent
    - 模型
    - 算法
  game:
    - 游戏
    - 手游
    - 主机
    - Steam
    - Switch
    - PS5
    - Xbox
    - 上线
    - 赛季
    - 联动
    - 版本
    - 新游
    - 发售
  device:
    - 芯片
    - 手机
    - 笔记本
    - 显卡
    - CPU
    - 处理器
    - iPhone
    - 系统
    - 发布
    - 评测
    - 新品
    - 上市
    - 小米
    - 华为
    - 苹果

schedule:
  collect: ["0:00", "3:00", "6:00", "12:00", "15:00", "18:00"]
  push: ["9:00", "21:00"]

pusher:
  wecom_webhook: "..."
```

## 9. 验收标准

1. `python main.py --push` 输出早晚报各 5 条/分类
2. 每分类两源至少各 1 条
3. 当天新闻不被降权，昨天及更早被降权
4. HTML 标签无残留
5. HF 条目标题含 `[EN]`
6. `pytest tests/` 全部通过
