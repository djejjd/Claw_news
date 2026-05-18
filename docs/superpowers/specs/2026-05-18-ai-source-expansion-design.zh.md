# AI 信息源扩展设计文档

## 1. 目标

在不改变当前服务化主链路的前提下，对统一 AI 日报做三项有边界的扩展：

1. 将当前“实际近似单源”的 AI RSS 入池链路升级为可配置的多源链路
2. 将 GitHub 仓库作为日报补充栏接入，但不让仓库条目参与核心新闻 TopN 竞争
3. 增加 ingest 可观测性，让服务器端可以直接看到最近一次抓取是否正常运行

本轮必须保留现有新闻评分模型，不借机重做主链路。

## 2. 当前状态

当前正式 ingest 任务会运行：

1. `RssCollector()`
2. `HfDailyPapersCollector()`

`RssCollector()` 内置了 4 个 feed，但只有 `qbitai` 被标记为 `category="ai"`。正式发布链路又固定为 `ai_only`，因此 `sspai`、`ithome`、`yystv` 会在进入 AI 候选池前被过滤掉。也就是说，当 HuggingFace 因网络原因不可用时，正式 AI 日报会退化成几乎只有量子位一个来源。

GitHub 当前并没有 collector。Task006 当时把“GitHub 热点正式接入”列为 out of scope，是为了先完成主链路统一，再考虑新增来源类型。

## 3. 设计结论

### 3.1 AI RSS：内置默认源 + 环境变量覆盖

新增专门的 AI RSS 配置层：

1. 代码内置一组小而稳定的默认 AI 源，确保新部署默认不是单源
2. 允许通过 `.env` 追加或完全替换内置 AI RSS 源
3. 每个配置源必须同时保留：
   - 稳定的 `source` 名称
   - 明确的 `category="ai"`

建议公开配置格式：

```dotenv
AI_RSS_FEEDS=qbitai|https://www.qbitai.com/feed,openai_blog|https://openai.com/news/rss.xml
AI_RSS_MODE=append
```

规则：

1. `AI_RSS_MODE=append`：保留内置源，并追加环境变量中的源
2. `AI_RSS_MODE=replace`：只使用环境变量中的源
3. 对非法或缺失字段的配置，在加载阶段直接拒绝，不要静默生成无名 feed
4. 不复用旧的 `NEWS_RSS_URLS`，因为它只有 URL，没有 `source` 身份和分类语义，接入后会让评分与观测继续变糊

### 3.2 GitHub：补充栏，不参与主排名

新增 `GitHubCollector`，基于 GitHub Search API 拉取 AI 相关仓库，并返回独立于 `CandidateItem` 的仓库 DTO。

首版查询策略建议：

1. 使用 topic 约束，例如 `topic:llm`、`topic:artificial-intelligence`、`topic:machine-learning`
2. 通过 Search API 参数按近期活跃度或 stars 排序
3. 控制为少量结果
4. 至少保留以下字段，用于日报渲染：
   - 仓库名
   - URL
   - 简介
   - stars
   - 主语言

GitHub 项目**不进入** `Merger(top_n=5)`。它们在主摘要之后渲染为独立补充段，例如：

```text
今日值得看项目
1. owner/repo — 简短说明
```

这样主日报仍然表达“今日新闻”，GitHub 则承担“值得顺手看一眼的项目发现”角色，不把两种信号硬混成一种。

首版固定展示 `3` 条 GitHub 项目，作为主摘要后的轻量补充，不做动态扩容。

### 3.3 Pipeline 形状

```text
高频 ingest
├─ AI RSS collectors -> CandidateItem 候选池
└─ GitHub collector   -> GitHub 快照存储

发布 pipeline
├─ AI 候选池      -> classifier -> merger -> LLM -> 主摘要
├─ GitHub 快照    -> 补充栏渲染输入
└─ 单条 WeCom markdown 消息，包含两个段落
```

最终仍只发送一条 WeCom markdown 消息。

### 3.4 ingest 可观测性

当前系统已经具备“定时抓取 -> 写入候选池 -> 定时发布读池”的结构，但缺少足够直接的运行观测。  
本轮新增一份轻量 ingest 状态，用于回答：

1. 最近一次 ingest 何时运行
2. 最近一次 ingest 写入了多少候选
3. 哪些来源成功
4. 哪些来源失败

设计结论：

1. 将最近一次 ingest 状态持久化到文件
2. 直接扩展现有 `/health` 返回值，而不是新增单独接口
3. `/health` 保持轻量，只暴露运行状态摘要，不承载候选内容本身

建议最小状态字段：

1. `last_ingest_at`
2. `last_item_count`
3. `successful_sources`
4. `failed_sources`

这样服务健康检查不再只是“进程还在”，而是能表达“抓取链路是否仍在呼吸”。

## 4. 数据模型

### 4.1 AI RSS 配置

使用一个小型配置 DTO 或辅助结构，至少包含：

1. `source`
2. `url`
3. `category="ai"`

### 4.2 GitHub 仓库条目

新增独立的仓库模型，不复用 `CandidateItem`：

1. `full_name`
2. `url`
3. `description`
4. `stars`
5. `language`
6. `fetched_at`

原因：仓库发现不是新闻文章。如果复用 `CandidateItem`，会模糊领域语义，也会诱发后续把仓库强行并进新闻评分的捷径。

### 4.3 持久化

使用与 ingestion store 并行的轻量文件快照，例如：

```text
data/github/YYYY-MM-DD/repos.json
```

这样可以：

1. 将 GitHub 抓取与发布时间解耦
2. 让服务器上的 GitHub 数据可直接检查
3. 保持当前文件型架构，不引入额外存储复杂度

### 4.4 ingest 状态

使用轻量文件保存最近一次 ingest 摘要，例如：

```text
data/ingestion_status.json
```

最小字段：

1. `last_ingest_at`
2. `last_item_count`
3. `successful_sources`
4. `failed_sources`

该状态只用于运行观测，不替代 `index.json`，也不参与正式发布逻辑。

## 5. 失败处理

1. 单个 AI RSS 源失败只影响该源，不拖死整轮 ingest
2. GitHub 失败不得阻断主 AI 日报
3. 若 GitHub 快照不可用，仍正常发布没有补充栏的主摘要
4. HuggingFace 继续保持 best-effort；在被网络阻断时要优雅降级
5. 单个来源失败时，ingest 状态必须能够如实记录，避免健康检查只显示“服务存活”却隐藏抓取退化

## 6. 测试策略

1. AI RSS 配置解析：
   - 仅默认源
   - append 模式
   - replace 模式
   - 非法配置拒绝
2. ingest 覆盖：
   - 配置后的 AI RSS 源能够进入 AI 候选池
3. GitHub collector：
   - 能将 API 响应解析为仓库 DTO
   - 能处理空结果与失败响应
4. 渲染：
   - 没有 GitHub 条目时，主摘要保持不变
   - 有 GitHub 条目时，补充栏正确出现
5. 发布行为：
   - GitHub 条目永远不进入 headline TopN
   - GitHub 失败不会导致主摘要失败
6. 可观测性：
   - 每次 ingest 会更新最近一次状态
   - `/health` 会返回 ingest 状态摘要
   - 单源失败会进入 `failed_sources`

## 7. 明确不做

本轮不做：

1. GitHub Trending HTML 抓取
2. 仓库 README 摘要
3. 让 GitHub 仓库与新闻标题竞争同一个 TopN
4. 数据库持久化
5. 超出当前 AI 日报范围的大型内容分类体系
