# T2 日报 API

---
状态: review_pending
最后更新: 2026-08-16
关联:
  - ../v1.1.0-公共内容API.md
  - ../../../架构/公共内容API设计.md
  - T1-公共读取仓储与契约.md
---

## 任务元信息

| 项目 | 内容 |
|---|---|
| 任务编号 | `v1.1.0-T2` |
| 依赖任务 | `v1.1.0-T1` 已完成并通过主审核 |
| 允许并行 | 无；与 T3/T4 共享公共路由模块，按 T2 → T3 → T4 顺序实现 |
| 允许修改路径 | `app/publication/routes.py`, `app/main.py`, `tests/test_public_api.py`, `tests/test_app_api.py`, `docs/计划/网站/v1.1.0/T2-日报API.md` |
| 禁止修改路径 | `app/publication/store.py`, `app/publication/public_api.py`, `app/publication/models.py`, `alembic/**`, `app/scheduler/jobs.py`, `collectors/**`, `aggregator/**`, `pusher/**`, `infra/**`, `frontend/**` |
| 启动审查结论 | `approved`（2026-08-16：独立启动审查确认 T1 依赖、日报契约、路由拆分、测试矩阵与文件边界均满足实施条件） |
| 主审核结论 | `approved`（2026-08-16：独立主审核确认日报契约、错误脱敏、公开字段、时区和读取无副作用均符合设计；整改反向测试已复核） |
| 任务提交 | `pending` |
| 完成状态 | review_pending：实现、检查与主审核完成，等待任务级提交 |
| 设计基线 | 《公共内容 API 设计》：`610c77cfc927f10564d973c9af4d37c4b38cdf58` |

## 接口变更表

| 变更 | 接口 | 参数 | 返回 | 错误 | 兼容性 | 测试 |
|---|---|---|---|---|
| 新增 | `GET /api/public/digests` | `date?: YYYY-MM-DD` | `200 DigestPublic` | 422/404/503 | `/`、`/health`、`POST /run/news` 不变 | `test_public_api.py`、`test_app_api.py` |

## 1. 背景

公共日报是 v1.2.0 首页的首个真实数据入口。日报是按自然日定版的资源，不能以内部 `Digest` ORM 或日报审计字段直接对外序列化。

## 2. 目标

实现 `GET /api/public/digests?date=`，通过 T1 读取边界返回当天或指定自然日的公共日报。

## 3. 前置依赖

- T1 的公开 DTO、读取仓储、时区边界和统一错误模型已可用；
- `Digest`、`DigestItem`、`DigestGitHubProject` 均来自同一已发布日报；
- 版本总览规定未传 `date` 时取 `config.tz` 当天。

## 4. 输入与输出契约

输入：可选的 `date=YYYY-MM-DD`。

输出：

- `200`：`date`、`version`、`published_at`、`daily_judgement`、按 `position` 排序的公开日报项和 GitHub 推荐；
- 日报项仅含公开文章字段及 `position`、`core_summary`、`importance`、`trend`、`topic_label`；GitHub 推荐仅含 `position`、`full_name`、`recommendation`；
- 未传日期取当地当天；格式非法返回 `422/invalid_request`；不存在返回 `404/digest_not_found`；发布库不可用返回 `503/publication_unavailable`。

## 5. 修改范围

1. 新增 `app/publication/routes.py`，增加日报端点和请求校验。
2. 在 `app/main.py` 注册公共路由，不改变既有 `/`、`/health`、`/run/news` 行为。
3. 增加 FastAPI 到 SQLite 的日报端到端测试和异常测试。

## 6. 禁止事项

- 不增加文章、来源、认证或管理端点；
- 不从候选池、JSON 或 LLM 临时补齐日报；
- 不暴露 `relevance`、`final_score`、内部状态或错误；
- 不在请求中写入或触发调度。

## 7. 执行要求

- 先为成功、缺省日期、非法日期、日报不存在和数据库不可用写失败测试；
- 使用 T1 DTO，不得在路由内手写不受约束的字典；
- 断言日报项和项目推荐的顺序及字段完整等值；
- 验证一次请求前后发布表与 JSON 状态均未变化。

## 8. 实施步骤

1. 在 `tests/test_public_api.py` 与 `tests/test_app_api.py` 编写端点契约测试，确认路由未注册时失败。
2. 在 `app/publication/routes.py` 注册最小路由，并由 `app/main.py` 挂载后调用 T1 查询接口。
3. 实现日期校验和统一错误转换。
4. 运行精确测试、完整 diff 检查并提交主审核。

## 9. 验收标准

1. 未登录客户端可读取当天或指定日期的已发布日报。
2. 缺省、非法和不存在日期严格符合约定状态码和响应结构。
3. 内部相关性、评分和数据库字段不泄露。
4. 端点不触发采集、LLM、投递或写操作。

## 10. 检查命令

```bash
./venv/bin/pytest tests/test_public_api.py tests/test_app_api.py -v
make lint
./venv/bin/ruff format --check .
```

### 实施检查记录

- `./venv/bin/pytest tests/test_public_api.py tests/test_app_api.py -v`：30 passed；
- `make test`：680 passed、1 skipped（既有人工标注校准门禁）；
- `make lint` 与 `./venv/bin/ruff format --check .`：通过；
- `make task-gate TASK=docs/计划/网站/v1.1.0/T2-日报API.md`：实现前通过；实现完成后转入本审核状态。

## 11. 交付前自检

- 已覆盖日期、空数据、错误和字段脱敏；
- 已验证顺序、JSON 结构和查询无副作用；
- 未修改路由以外的生产流程；
- 已检查 diff 中无敏感信息。

## 12. 交付格式

按仓库固定交付格式交付；主审核重点为日报 DTO 白名单、错误转换和读取无副作用。
