# T6 PostgreSQL 读取与清理验收

---
状态: review_pending
最后更新: 2026-08-16
关联:
  - ../v1.1.0-公共内容API.md
  - ../../../架构/公共内容API设计.md
  - ../../待办.md
  - T1-公共读取仓储与契约.md
  - T2-日报API.md
  - T3-新闻流分页与过期清理.md
  - T4-来源API.md
  - T5-契约回归与版本验收.md
---

## 任务元信息

| 项目 | 内容 |
|---|---|
| 任务编号 | `v1.1.0-T6` |
| 依赖任务 | `v1.1.0-T1` 至 `v1.1.0-T5` 已完成并通过主审核 |
| 允许并行 | 无；验证公共读取与清理的已冻结契约 |
| 允许修改路径 | `docs/计划/网站/v1.1.0/T6-PostgreSQL读取与清理验收.md`, `docs/计划/待办.md`, `docs/计划/网站/v1.1.0-公共内容API.md`, `docs/计划/网站开发版本计划.md` |
| 禁止修改路径 | `app/**`, `alembic/**`, `tests/**`, `collectors/**`, `aggregator/**`, `pusher/**`, `infra/**`, `frontend/**`, `pyproject.toml`, `CHANGELOG.md`, `Dockerfile`, `docker-compose.yml` |
| 启动审查结论 | `approved`（2026-08-16：独立启动审查复核已批准设计基线、T1-T5 completed/approved 依赖、固定数据矩阵、故障隔离到达条件、允许/禁止路径、非 main 分支与工作区范围；无并行冲突，准许启用 T6。） |
| 主审核结论 | `approved`（2026-08-16：独立主审核复核隔离 PostgreSQL 迁移、三端点、两轮清理计数、五类调度故障隔离、临时脚本无真实采集/仓库状态写入，以及版本计划状态同步；无阻断问题。） |
| 任务提交 | `pending` |
| 完成状态 | review_pending：隔离 PostgreSQL 验证、指定回归与质量检查已完成，等待独立主审核。 |
| 设计基线 | 《公共内容 API 设计》：`610c77cfc927f10564d973c9af4d37c4b38cdf58` |

## 接口变更表

| 变更 | 接口/入口 | 输入 | 输出 | 副作用 | 测试 |
|---|---|---|---|---|---|
| 保持不变 | 三条公共端点、发布库清理与 ingest 清理 | 隔离 PostgreSQL 验证数据 | 真实数据库验收证据 | 仅隔离验证库写入 | 端点、两轮清理、失败隔离 |

## 1. 背景

`WEB-V1.1.0-PG-READ-CLEANUP-01` 要求补齐 SQLite 之外的 PostgreSQL 读取、清理事务和调度集成证据，作为 v1.1.0 标记完成与发布的前置条件。

## 2. 目标

在隔离 PostgreSQL 数据库构造固定数据，验证三条公共端点、十日清理两轮状态变化和高频 ingest 清理失败隔离。

## 3. 前置依赖

- T1-T5 均已完成且主审核通过；
- 使用非生产、名称带验证标识的独立数据库；
- 执行前确认 PostgreSQL 版本、连接目标和数据库为空。

## 4. 输入与输出契约

输入：PostgreSQL 16 验证库、`PUBLICATION_DATABASE_URL`、固定为 `2026-08-16` 的公开/隐藏/窗口边界文章、日报和来源。

输出：仅在本任务包中记录迁移版本、脱敏数据库标识、三端点响应、两次清理的文章/关联/日报计数，以及候选池、发布库和状态记录失败时清理隔离证据。命令以变量名和容器/数据库别名记录，不记录连接串或密码。

## 5. 修改范围

只记录验证命令、脱敏连接目标、结果和待办/版本状态；不修改业务实现、测试或迁移。

## 6. 禁止事项

- 不连接、清空或写入生产数据库；
- 不记录密码、连接串或其他密钥；
- 不以构造数据替代接口、事务和调度的实际 PostgreSQL 执行；
- 验收失败时不得标记版本完成。

## 7. 执行要求

- 先运行 `alembic upgrade head`，记录 PostgreSQL 版本和迁移版本；
- 构造第十天保留、第十一天清理、隐藏文章、公开/隐藏日报关联及多来源数据；
- 实际调用三条端点、两次清理和 `run_ingest_with_cleanup()`；
- 分别令候选池清理、发布库清理和降级状态读写失败，证明两类清理仍分别尝试、ingest 成功返回不变，且 ingest 原始异常保持抛出；
- 记录每步计数和失败隔离结果，清理验证库仅在结果已记录后执行。

### 固定造数与预期矩阵

统一时区为 `Asia/Shanghai`，`local_today=2026-08-16`。临时脚本写入以下固定记录：

| canonical key / source | UTC `fetched_at` / visibility | 日报关联 | 精确预期 |
|---|---|---|---|
| `expired-only` / `alpha`（display `Alpha`） | `2026-08-06T04:00:00+00:00` / published | 2026-08-06 过期日报 | 首轮标记并删除；该日报含 1 item、1 GitHub 推荐 |
| `retained-boundary` / `beta`（display `Beta`） | `2026-08-07T04:00:00+00:00` / published | 无 | 第十天保留，三条端点可见 |
| `old-retained-digest` / `alpha` | `2026-08-06T04:00:00+00:00` / published | 2026-08-16 公开日报 | 首轮保留，避免保留日报悬空；该日报返回 `200` |
| `hidden-current` / `hidden` | `2026-08-16T04:00:00+00:00` / hidden | 2026-08-15 隐藏关联日报 | articles/sources 排除；该日报返回 `404` |
| `alpha-current` / `alpha`（display `Alpha`） | `2026-08-16T04:00:00+00:00` / published | 无 | 十日新闻流可见，保证默认新闻流 `total=4` 且来源含 `Alpha` |
| `same-a`、`same-b` / `same-a`、`same-b`（均 display `Same`） | `2026-08-16T04:00:00+00:00` / published | 无 | sources 按 `Alpha,Beta,Same/same-a,Same/same-b`；重复文章不重复来源 |

清理前计数：articles=7、digests=3、digest_items=3、GitHub=1。首轮精确结果：marked/deleted articles=1、deleted digest_items=1、deleted GitHub=1、deleted digests=1，清理后为 articles=6、digests=2、digest_items=2、GitHub=0。第二轮全部删除结果为 0，计数不变。

端点由 `TestClient` 调用：`/api/public/digests?date=2026-08-16` 返回公开保留日报及字段白名单；`/api/public/digests?date=2026-08-15` 因隐藏关联返回 `404`；`/api/public/articles?page=1&page_size=20` 不含 hidden/expired 且 `total=4`；`/api/public/sources` 为上述稳定顺序且仅含 `name,display_name,site_url`；禁用数据库时三条均为脱敏 `503`。

### 故障隔离矩阵

| 注入点 | 必须观察 | ingest 成功路径 | ingest 异常路径 |
|---|---|---|---|
| 候选池 `prune_expired` 抛错 | 发布库 `cleanup_expired_publication` 仍调用 | 原始返回值不变 | 原始异常仍抛出 |
| 发布库 `cleanup_expired_publication` 抛错 | 候选池清理已尝试；降级记录尝试 | 原始返回值不变 | 原始异常仍抛出 |
| `IngestStatusStore.load_status` 抛错 | 固定令发布库清理先抛错以进入降级分支；候选池与发布库清理均已尝试，`load_status` 实际调用，状态写入不外泄 | 原始返回值不变 | 原始异常仍抛出 |
| `IngestStatusStore.write_status` 抛错 | 固定令发布库清理先抛错以进入降级分支；候选池与发布库清理均已尝试，`write_status` 实际调用 | 原始返回值不变 | 原始异常仍抛出 |
| `run_ingest` 抛错 | 两类清理均尝试 | 不适用 | 保持原始异常类型和消息 |

### 临时脚本隔离要求

- 脚本只可创建并使用 `TemporaryDirectory` 下的状态文件路径；不得读取、写入或依赖仓库 `data/`。
- 故障隔离验证必须 patch `app.scheduler.jobs.run_ingest`：成功路径使用固定返回值，异常路径使用固定异常；因此不得触发真实 collector、网络请求或采集写入。
- 必须以 mock 替代 `app.scheduler.jobs.IngestionStore`、`IngestStatusStore` 和 `app.publication.publisher.Publisher.from_config`，并将 `app.scheduler.jobs._DATA_DIR` 指向临时目录；断言实际调用的是 mock，而非仓库状态文件。
- 五个注入点逐项独立执行：候选池 `prune_expired`、发布库 `cleanup_expired_publication`、状态 `load_status`、状态 `write_status` 和 `run_ingest`。验证状态 `load_status`、`write_status` 时，必须固定令 `cleanup_expired_publication` 先抛异常以到达降级分支；该前置异常不替代状态故障注入。每项都须断言两类清理的调用、状态方法实际调用、成功返回值不变或原始异常类型与消息不变。

## 8. 实施步骤

1. 核对隔离容器和数据库目标，迁移至 head。
2. 写入固定验收数据并执行三条端点读取。
3. 执行两轮清理，记录状态和计数变化。
4. 在临时目录中以 mock 分别模拟五类清理/状态故障，确认不触发真实采集或仓库状态文件，且清理独立尝试、ingest 成功返回不变、原始异常保持不变。
5. 更新待办与版本计划，提交主审核。

## 9. 验收标准

1. 三条端点在 PostgreSQL 上满足公开字段、窗口、排序和脱敏错误契约。
2. 第十天内容保留、第十一天按设计顺序清理，第二轮幂等。
3. 候选池、发布库和降级状态记录任一失败均不阻断另一清理；临时故障验证不触发真实采集或仓库 `data/` 写入，ingest 成功返回保持不变，原始 ingest 异常保持抛出。
4. `WEB-V1.1.0-PG-READ-CLEANUP-01` 有完整关闭证据后才解除版本阻塞。

## 10. 检查命令

```bash
export VALIDATION_DB=claw_news_v110_verify
export PUBLICATION_DATABASE_URL="postgresql+psycopg://claw:${PG_PASSWORD}@127.0.0.1:55432/${VALIDATION_DB}"
export PUBLICATION_ENABLED=1
export TZ=Asia/Shanghai
./venv/bin/alembic upgrade head
# 以临时脚本 /private/tmp/claw_news_v110_pg_verify.py 连接 ${VALIDATION_DB}：先 seed，再以 TestClient 调用三端点、两轮 cleanup；故障隔离部分必须按“临时脚本隔离要求”以 mock 和 TemporaryDirectory 执行五个注入点。脚本和输出均不入库且不输出连接串。
./venv/bin/python /private/tmp/claw_news_v110_pg_verify.py
./venv/bin/pytest tests/test_publication_store.py tests/test_public_api.py tests/test_ingest_job.py -v
make lint
./venv/bin/ruff format --check .
```

## 验收记录

- 验证目标：本机隔离容器 `claw-news-postgres-test` 的 `claw_news_v110_verify`；仅绑定 `127.0.0.1:55432`，PostgreSQL `16.14`。执行前该数据库不存在；迁移后版本为 `20260815_01`。
- 执行命令：以 `VALIDATION_DB=claw_news_v110_verify`、`PUBLICATION_ENABLED=1`、`TZ=Asia/Shanghai` 和仅在进程环境中组装的 `PUBLICATION_DATABASE_URL` 运行 `./venv/bin/alembic upgrade head`，再运行 `/private/tmp/claw_news_v110_pg_verify.py`。命令与输出均未记录连接串或密码。
- 端点结果：`GET /api/public/digests?date=2026-08-16` 为 `200` 且仅含公开字段；`GET /api/public/digests?date=2026-08-15` 为 `404/digest_not_found`；`GET /api/public/articles?page=1&page_size=20` 的 `total=4`；`GET /api/public/sources` 为 `alpha,beta,same-a,same-b`。禁用发布库后三条端点均为 `503/publication_unavailable`。
- 清理结果：清理前 `articles=7,digests=3,digest_items=3,github_projects=1`；首轮删除 1 篇文章、1 条日报项、1 个 GitHub 推荐和 1 份日报，结果为 `6,2,2,0`；第二轮各删除数均为 0，计数不变。保留日报关联的 8 月 6 日文章未被删除。
- 调度故障隔离：临时脚本在 `TemporaryDirectory` 中 mock `run_ingest`、候选池、状态存储和发布器，五个注入点 `candidate`、`publication`、`load_status`、`write_status`、`ingest` 均通过；真实 collector 和仓库 `data/` 均未调用。
- 回归与质量：`./venv/bin/pytest tests/test_publication_store.py tests/test_public_api.py tests/test_ingest_job.py -v` 为 `57 passed`；`make lint` 通过；`./venv/bin/ruff format --check .` 为 `127 files already formatted`。

## 11. 交付前自检

- [x] 已确认数据库为隔离验证目标；
- [x] 记录不含密码或连接串；
- [x] 每个端点、两轮清理和失败隔离均有实际证据；
- [x] 故障隔离脚本已证明不触发真实 collector，且没有读写仓库 `data/`；
- [ ] 待办和版本状态与验证结果一致（等待主审核批准后关闭）。

## 12. 交付格式

按仓库固定交付格式交付；主审核重点为隔离目标、真实 PostgreSQL 证据、清理计数和版本阻塞解除依据。
