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
| 🤖 AI | HuggingFace Daily Papers | API | 5 条 | API upvotes（自带） |
| 🤖 AI | 量子位 | RSS + 富化 | 5 条 | 原文页面阅读量 |
| 🎮 Game | TapTap 下载榜 | 爬虫 | 5 条 | 榜单排名（自带） |
| 🎮 Game | 游研社 | RSS + 富化 | 5 条 | 原文页面阅读/评论 |
| 📱 Device | IT之家 | RSS + 富化 | 5 条 | 原文页面阅读量+评论数 |
| 📱 Device | 少数派 | RSS + 富化 | 5 条 | 原文页面阅读量 |

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

### 4.1 接口

```python
# collectors/enricher.py

class Enricher:
    def __init__(self, client: httpx.AsyncClient | None = None): ...

    async def enrich(self, items: List[HotItem]) -> List[HotItem]:
        """
        对 HotItem 列表进行富化：
        - 已有 source_score ≠ 5.0 的跳过（HF、TapTap 自带热度）
        - source_score == 5.0 的 RSS 条目根据 source 字段路由到对应提取器
        - 并发访问原文页面获取热度指标
        - 热度指标归一化为 source_score（0-10）
        """
```

### 4.2 各源提取策略

| 源 | 提取字段 | 归一化方式 |
|----|---------|-----------|
| 量子位 | 阅读量 | 同类阅读量最高者=10，其他按比例 |
| IT之家 | 阅读量 + 评论数 | 评论数加权（1评论=10阅读），取最大者=10 |
| 少数派 | 阅读量 | 同类阅读量最高者=10，其他按比例 |
| 游研社 | 阅读量 + 评论数 | 同 IT之家策略 |

### 4.3 容错

- 原文页面访问失败 → 保留 source_score = 5.0，不中断
- 页面解析不到热度数据 → 保留 source_score = 5.0
- 单条富化超时 15s，超时跳过

## 5. 聚合层设计（更新）

### 5.1 每源取 5 条

配置项 `fetch_count: 5`，采集器统一遵守。

### 5.2 竞争规则

每个分类 2 个源，各产 5 条，合并 10 条 → 输出 5 条：

```
前 3 条：全量 10 条按 final_score 自由竞争，取最高 3 条
后 2 条：每源各保底 1 条，取该源剩余条目中 final_score 最高者
```

示例（AI 分类：HF 5条 + 量子位 5条）：

```
Step 1:  10条按 final_score 降序 → 取 top 3（可能是 HF:2 + 量子位:1）
Step 2:  HF 剩余 3 条 → 取最高 1 条保底
Step 3:  量子位剩余 4 条 → 取最高 1 条保底
Result:  5 条，每源至少 1 条，最多 4 条
```

### 5.3 评分公式

```
final_score = source_score（热度归一化 0-10）+ time_decay_bonus（时效分）
```

- 已有热度数据的源（HF、TapTap）：source_score 来源于采集阶段
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
│   ├── huggingface.py         # 改：fetch_count=5
│   ├── rss_sources.py         # 改：fetch_count=5, 机器之心→量子位, HTML去标签
│   ├── taptap.py              # 改：fetch_count=5
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
  fetch_count: 5  # 每个源取几条
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
| 并发富化 20 条导致请求过多 | 限制并发数 5，asyncio.Semaphore |
| 量子位 RSS 后续也关站 | RSS feed 解析 bozo 标识，失败不中断 |
| 网站反爬封 IP | 富化使用和采集器相同的 UA header |

## 10. 验收标准

1. `python main.py --dry-run` 输出每分类 5 条，每源至少 1 条
2. RSS 条目标题旁无 HTML 标签残留
3. HF 条目标题含 `[EN]` 标记
4. `pytest tests/` 全部通过
5. `python main.py` 推送成功，手机收到三条消息
