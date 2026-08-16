---
状态: approved
最后更新: 2026-08-16
关联:
  - 网站平台设计.md
  - ../规范/接口设计规范.md
  - ../计划/网站/v1.1.0-公共内容API.md
---

# 公共内容 API 设计

## 决策与批准

| 状态 | 批准角色 | 批准日期 | 设计基线 | 待决问题 |
|---|---|---|---|---|
| `approved` | 用户已于 2026-08-16 确认语义；主审核已通过 | 2026-08-16 | `610c77cfc927f10564d973c9af4d37c4b38cdf58` | 无；后续变更须重新批准 |

## 范围与边界

接口只读 PostgreSQL 发布库，仅展示 `published` 内容；不触发采集、LLM、消息投递、JSON 回退或任何写入。日期按 `config.tz` 解释，时间字段均为带时区 ISO 8601。

## 接口变更

| 变更 | 接口与调用者 | 认证 | 参数 | 成功输出 | 错误 | 兼容性 |
|---|---|---|---|---|
| 新增 | `GET /api/public/digests`；v1.2 公共前端 | 无 | `date?: YYYY-MM-DD`，缺省为当地当天 | `200 DigestPublic` | 422/404/503 | 不修改既有路由 |
| 新增 | `GET /api/public/articles`；v1.2 公共前端 | 无 | `date?`、`source?`、`page=1`、`page_size=20`，范围 1-50 | `200 ArticlePage` | 422/503 | 不修改既有路由 |
| 新增 | `GET /api/public/sources`；v1.2 公共前端 | 无 | 无 | `200 SourcePublic[]` | 503 | 不修改既有路由 |

有效但窗口外日期、未知来源和超末页返回空文章列表；日报不存在返回 `404`。

## 公开字段

| DTO | 字段（类型；可空） | 来源 | 不公开字段 |
|---|---|---|---|
| `ArticlePublic` | `id:int,title:string,original_url:string,category:string,topic:string?,summary:string,published_at:string?,fetched_at:string,source:SourcePublic` | `articles` 与 `sources` | `canonical_key,visibility,topic_confidence` |
| `SourcePublic` | `name:string,display_name:string,site_url:string?` | `sources` | feed、策略、健康、订阅默认值、启用状态 |
| `DigestPublic` | `date:string,version:int,published_at:string,daily_judgement:string,items:DigestItemPublic[],github_projects:GitHubProjectPublic[]` | `digests` 及关联 | `status,relevance,final_score` |
| `DigestItemPublic` | `position:int,core_summary:string,importance:string,trend:string,topic_label:string?,article:ArticlePublic` | `digest_items` 与文章 | `relevance` |
| `GitHubProjectPublic` | `position:int,full_name:string,recommendation:string` | `digest_github_projects` | `final_score` |

`summary` 映射 `source_summary`，缺失时为空字符串。新闻按 `published_at`（缺失时 `fetched_at`）倒序，再按 `id` 排序。来源按 `display_name,name` 排序，且当前十天内至少关联一条公开文章。

## 错误响应

```json
{"detail": {"code": "invalid_request", "message": "请求参数无效"}}
```

统一使用 `invalid_request`（422，`请求参数无效`）、`digest_not_found`（404，`指定日期不存在已发布日报`）和 `publication_unavailable`（503，`公共内容服务暂不可用`）；响应不得暴露 Pydantic、SQLAlchemy、数据库连接或密钥信息。

| 场景 | 状态码/错误码 | 副作用 | 日志要求 |
|---|---|---|---|
| 参数非法 | `422/invalid_request` | 无 | 不记录参数原文中的敏感值 |
| 日报不存在或不满足公开条件 | `404/digest_not_found` | 无 | 不暴露存在性细节 |
| 发布库未启用或不可用 | `503/publication_unavailable` | 无 | 记录异常类型，不记录连接串 |

## 响应示例

```json
{"date":"2026-08-16","version":1,"published_at":"2026-08-16T09:00:00+08:00","daily_judgement":"今日摘要","items":[{"position":1,"core_summary":"摘要","importance":"high","trend":"up","topic_label":null,"article":{"id":1,"title":"标题","original_url":"https://example.invalid/a","category":"ai","topic":null,"summary":"","published_at":null,"fetched_at":"2026-08-16T08:00:00+08:00","source":{"name":"example","display_name":"示例来源","site_url":null}}}],"github_projects":[]}
```

`/articles` 成功返回 `{"items":[ArticlePublic],"page":1,"page_size":20,"total":1}`；`/sources` 成功返回 `[SourcePublic]`。三条端点失败均使用上节错误 DTO，例如 `{"detail":{"code":"publication_unavailable","message":"公共内容服务暂不可用"}}`。

```json
{"items":[{"id":1,"title":"标题","original_url":"https://example.invalid/a","category":"ai","topic":null,"summary":"","published_at":null,"fetched_at":"2026-08-16T08:00:00+08:00","source":{"name":"example","display_name":"示例来源","site_url":null}}],"page":1,"page_size":20,"total":1}
```

```json
[{"name":"example","display_name":"示例来源","site_url":null}]
```

```json
{"detail":{"code":"invalid_request","message":"请求参数无效"}}
```

```json
{"detail":{"code":"digest_not_found","message":"指定日期不存在已发布日报"}}
```

## 保留与清理

令 `local_today = local_now(config.tz).date()`，保留窗口为 `[local_today - 9 days, local_today]`。文章以 `fetched_at` 的当地日期、日报以 `digest_date` 判断；小于窗口起点即过期。`Digest.status` 只有 `published` 可公开，其他值一律不可公开。日报查询必须同时限制窗口、`Digest.status == "published"`，并要求其所有日报项关联文章仍为 `published`；否则整份日报返回 `404/digest_not_found`。

既有高频 ingest 调度任务的 `finally` 分支触发清理。单一事务先识别过期日报和“已过期且未被保留窗口日报引用”的文章；将后一类文章标为 `expired`，再删除过期日报的 `digest_items`、`digest_github_projects`、`digests`，最后删除已标记文章。保留窗口内日报引用的旧文章保留到其最后一个保留日报过期，避免外键冲突和空日报。清理失败记录发布库降级，不影响采集或消息投递；公共查询绝不触发清理。

## 兼容性与非目标

既有 `/`、`/health`、`POST /run/news` 保持不变。本设计不包含认证、订阅、管理接口、前端、CORS、部署或历史回填。
