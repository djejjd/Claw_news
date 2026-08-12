# 每日热点聚合推送 V2 — 热度富化 + 源多样性竞争 设计文档

## 1. 变更背景

V1 存在的问题：
- RSS 源所有条目 `source_score = 5.0`，仅靠时间差区分，同分类两源无法真实比较热度
- 机器之心 RSS 已关站，需替换
- RSS 摘要含 HTML 标签未清理
- 同一源可能霸占分类 Top 5，缺少源多样性保障

## 2. 数据源（更新）

| 分类 | 源 | 方式 | 每次取 | 热度数据来源 |
|------|-----|------|--------|-------------|
| 🤖 AI | HuggingFace Daily Papers | API | 10 条 | API upvotes（自带） |
| 🤖 AI | 量子位 | RSS + 富化 | 10 条 | 原文页面阅读量 |
| 🎮 Game | TapTap 下载榜 | 爬虫 | 10 条 | 榜单排名（自带） |
| 🎮 Game | 游研社 | RSS + 富化 | 10 条 | 原文页面阅读/评论 |
| 📱 Device | IT之家 | RSS + 富化 | 10 条 | 原文页面阅读量+评论数 |
| 📱 Device | 少数派 | RSS + 富化 | 10 条 | 原文页面阅读量 |

> 量子位替换已关站的机器之心。

## 3. 架构设计

```
采集层 (collectors/)      富化层 (enricher/)       聚合层 (aggregator/)      推送层 (pusher/)
───────────────────      ────────────────        ───────────────────      ────────
                          ┌──────────────┐
huggingface ──────────┐   │ 量子位→阅读量  │        ┌──────────────┐
rss_sources ──────────┤   │ IT之家→阅读+评 │        │ Top3 全量竞争  │
taptap ───────────────┼→  │ 少数派→阅读量  │ ──────→│ 每源保底 1 条  │──→ WeCom Bot
                      ┘   │ 游研社→阅读+评 │        │ 输出 Top 5    │
                          └──────────────┘        └──────────────┘
```

**新文件**：
```
collectors/
├── enricher.py           # 富化入口 + 原文热度提取调度
├── enrichers/            # 按源拆分提取逻辑
│   ├── __init__.py
│   ├── qbitai.py         # 量子位
│   ├── ithome.py         # IT之家
│   ├── sspai.py          # 少数派
│   └── yystv.py          # 游研社
```

## 4. 富化层设计

### 4.1 当前 source_score 来源

| 源 | 当前 source_score | 问题 |
|----|------------------|------|
| HuggingFace | upvotes 归一化到 0-10 | ✅ 有意义 |
| TapTap | 榜单排名归一化到 0-10 | ✅ 有意义 |
| 量子位/IT之家/少数派/游研社 | 全部 5.0 | ❌ 无法区分热度 |

### 4.2 富化流程

```
所有条目（采集阶段产出）
  ↓
判断 source_score ≠ 5.0（HF/TapTap）→ 跳过热度提取，仅做关键词加权
判断 source_score == 5.0（RSS）→ 执行以下全部步骤
  ↓
步骤 1：访问原文页面 URL
  ↓
根据 source 路由到对应提取器
  ↓
从 HTML 中提取原始指标（阅读量/评论数）
  ↓
同一源内，指标归一化到 0-10（批次内相对竞争）
  ↓
步骤 2：关键词命中加权
  ↓
标题/摘要匹配对应分类关键词 → source_score + 1.0
未命中 → 不加
  ↓
更新 source_score
```

### 4.3 各源原始指标提取

| 源 | 提取字段 | 说明 |
|----|---------|------|
| 量子位 | `views`（阅读量） | 原文页面通常有阅读数 |
| IT之家 | `views`（阅读量）+ `comments`（评论数） | 两者都显示在文章页 |
| 少数派 | `views`（阅读量） | 文章页有阅读数 |
| 游研社 | `views`（阅读量）+ `comments`（评论数） | 同 IT之家 |

### 4.4 归一化公式

**单指标源（量子位、少数派）**：

```
source_score = (views / max_views_in_batch) × 10
```

**双指标源（IT之家、游研社）**：

```
heat = views + comments × 10    # 1 条评论 ≈ 10 次阅读
source_score = (heat / max_heat_in_batch) × 10
```

**边界处理**：

- `max_views_in_batch == 0`（全为 0）→ 全部保留 5.0（无法竞争）
- 批次仅 1 条 → source_score = 10.0（没有比较对象，按最高处理）
- 提取失败 → 保留 5.0，不中断其他条目

### 4.5 接口定义

```python
# collectors/enricher.py

class Enricher:
    """热度富化器：对 source_score=5.0 的 RSS 条目，从原文提取热度数据"""

    def __init__(self, client: httpx.AsyncClient | None = None): ...

    async def enrich(self, items: List[HotItem]) -> List[HotItem]:
        """
        输入：采集阶段产出的所有 HotItem（含 HF/TapTap 已评分 + RSS 默认 5.0）
        输出：富化后的 HotItem（RSS 条目的 source_score 替换为归一化热度）
        
        识别逻辑：
        - source_score != 5.0 → 跳过（已有热度数据）
        - source_score == 5.0 → 根据 item.source 路由到对应提取器
        
        并发控制：asyncio.Semaphore(5)
        超时：单条 15s
        """
```

### 4.6 提取器文件结构

```
collectors/enrichers/
├── __init__.py
├── qbitai.py         # extract(title, url) -> dict{views: int}
├── ithome.py         # extract(title, url) -> dict{views: int, comments: int}
├── sspai.py          # extract(title, url) -> dict{views: int}
└── yystv.py          # extract(title, url) -> dict{views: int, comments: int}
```

每个提取器暴露 `async def extract(url: str) -> dict`，返回原始指标字典。提取失败抛异常，由 Enricher 捕获处理。

### 4.7 关键词标记（不参与评分）

富化步骤 2。在标题和摘要中匹配对应分类的关键词，标记是否命中。关键词**不参与 source_score 计算**，仅影响后续竞争选品逻辑。

**关键词库**：

```yaml
# config.yaml 中新增
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
  game:
    - 游戏
    - 手游
    - 主机
    - Steam
    - Switch
    - PS5
    - 上线
    - 赛季
    - 联动
    - 版本
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
```

**匹配规则**：
- 对 `item.title + item.summary` 做小写匹配
- 命中对应分类下任意 1 个关键词 → 标记 `item.keyword_hit = True`
- 未命中 → `item.keyword_hit = False`

> `HotItem` 新增字段：`keyword_hit: bool = False`

## 5. 聚合层设计（更新）

### 5.1 每源取 10 条

配置项 `fetch_count: 10`，每个源采集 10 条，采集器统一遵守。每个分类 2 源 → 20 条竞争。

### 5.2 竞争规则

```
每个分类 20 条 = 源A 10条 + 源B 10条

Step 1 — 关键词保底（每源各 1 条）：
  源A 中筛选 keyword_hit=True 的条目 → 取 final_score 最高 1 条
  源A 中无命中 → 取源A全部剩余中 final_score 最高 1 条（兜底）
  源B 同理
  → 共 2 条，标记为「保底槽」

Step 2 — 全量竞争（剩余 3 条）：
  去除已入选的 2 条，剩余 18 条按 final_score 降序 → 取前 3 条
  → 这 3 条不区分来源，自由竞争

Step 3 — 最终排序：
  5 条按 final_score 降序排列展示
```

```
示例（AI：HF 10条 + 量子位 10条）：

  量子位命中：3条（score 8.5, 7.2, 4.1）
  HF 命中：   5条（score 9.8, 9.1, 8.0, 7.5, 6.3）

  Step 1: 量子位保底 = 8.5, HF 保底 = 9.8
  Step 2: 剩余 18 条竞争 → 取 top 3
  Step 3: 最终 5 条: [9.8(HF保底), 9.1(HF竞争), 8.5(量子位保底), 8.0(HF竞争), 7.5(HF竞争)]
  → 至少保证量子位出 1 条，其余按真实热度竞争
```

### 5.3 评分公式

```
final_score = source_score（热度归一化 0-10） + time_decay_bonus（时效分）
```

- 评分不涉及关键词权重，关键词仅作用于 Step 1 筛选
- HF/TapTap：source_score 来源于采集阶段
- RSS 源：source_score 来源于富化阶段
- 富化失败：source_score 回退为 5.0

## 6. 推送层改进

- `format_message`：摘要字段执行 `strip_html()` 去标签
- HF 条目标题前加 `[EN]` 标记
- 每源条目补一行来源标注（如 `— 量子位`）

## 7. 项目结构（更新后）

```
Claw_news/
├── main.py
├── config.yaml
├── collectors/
│   ├── base.py                # HotItem（不变）
│   ├── huggingface.py         # 改：fetch_count=10
│   ├── rss_sources.py         # 改：fetch_count=10, 机器之心→量子位, HTML去标签
│   ├── taptap.py              # 改：fetch_count=10
│   ├── enricher.py            # 新增：富化入口
│   └── enrichers/             # 新增：按源拆分
│       ├── __init__.py
│       ├── qbitai.py
│       ├── ithome.py
│       ├── sspai.py
│       └── yystv.py
├── aggregator/
│   └── merger.py              # 改：新竞争策略
├── pusher/
│   └── wecom.py               # 改：HTML去标签, [EN]标记, 来源标注
├── tests/
│   ├── test_enricher.py
│   └── （其他测试同步更新）
└── data/
```

## 8. 配置项（更新后）

```yaml
collectors:
  fetch_count: 10  # 每个源取几条
  sources:
    huggingface: true
    rss: true
    taptap: true
    ithome: false  # 已切到 RSS

rss_feeds:
  - url: "https://www.qbitai.com/feed"
    category: "ai"
  - url: "https://sspai.com/feed"
    category: "device"
  - url: "https://www.ithome.com/rss/"
    category: "device"
  - url: "https://www.yystv.cn/rss/feed"
    category: "game"

pusher:
  wecom_webhook: "..."

schedule:
  time: "09:00"
```

## 9. 风险与应对

| 风险 | 应对 |
|------|------|
| 原文页面结构变更导致热度提取失败 | 每条提取包裹 try/except，失败保留默认分 5.0 |
| 并发富化 40 条导致请求过多 | 限制并发数 5，asyncio.Semaphore |
| 量子位 RSS 后续也关站 | RSS feed 解析 bozo 标识，失败不中断 |
| 网站反爬封 IP | 富化使用和采集器相同的 UA header |

## 10. 验收标准

1. `python main.py --dry-run` 输出每分类 5 条，每源至少 1 条
2. RSS 条目标题旁无 HTML 标签残留
3. HF 条目标题含 `[EN]` 标记
4. `pytest tests/` 全部通过
5. `python main.py` 推送成功，手机收到三条消息
