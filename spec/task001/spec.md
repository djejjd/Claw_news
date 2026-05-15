# Claw_news M1+M2 Task Contract Spec

## Immutable Rule

本文件是当前任务的唯一验收契约。  
自确认后：

1. Review 只能基于本文件判断是否通过。
2. Review 不允许提出新的范围外阻塞项。
3. 新发现但不属于本文件范围的问题，必须记录到 `next_task`，不得阻塞当前任务。
4. 阻塞项必须能映射到本文件的“实现要求”或“验收标准”。
5. 禁止使用“建议优化”“最好”“可以考虑”作为阻塞理由。

---

## 任务目标

在不改变现有热点评分逻辑、分类逻辑、消息格式核心语义的前提下，完成 M1/M2 工程化改造，使项目达到以下目标：

1. 配置加载有单一入口，支持环境变量覆盖 webhook。
2. 推送按 category 独立提交状态，已成功 category 的状态不会因后续失败而丢失。
3. 企业微信响应同时校验 HTTP 状态和业务 `errcode`。
4. 任务运行具备单实例锁，避免并发重入。
5. 项目具备统一安装、测试、lint、CI 入口。
6. 文档与真实运行契约一致。

---

## 修改范围

本轮允许修改以下内容：

1. 运行编排层
   - `main.py`

2. 配置与状态边界
   - `infra/config/settings.py`
   - `infra/storage/state_store.py`
   - `infra/__init__.py`
   - `infra/config/__init__.py`
   - `infra/storage/__init__.py`

3. 推送层
   - `pusher/wecom.py`

4. 采集器配置注入相关
   - `collectors/rss_sources.py`
   - `collectors/huggingface.py`
   - `collectors/taptap.py`
   - `collectors/utils.py`

5. 测试
   - `tests/test_settings.py`
   - `tests/test_state_store.py`
   - `tests/test_main.py`
   - `tests/test_wecom.py`
   - `tests/test_resilience.py`
   - `tests/test_rss_collector.py`
   - 为兼容本轮改动而必要调整的现有测试文件

6. 工程化文件
   - `pyproject.toml`
   - `Makefile`
   - `.github/workflows/ci.yml`
   - `.env.example`
   - `.gitignore`
   - `requirements.txt`

7. 文档与部署说明
   - `README.md`
   - `deploy.example.sh`

---

## 禁止修改范围

本轮禁止把以下内容作为实现目标或阻塞 review 的依据：

1. 评分逻辑重构
   - `aggregator/merger.py` 的业务规则
   - `collectors/base.py` 的评分模型含义

2. 新的数据存储方案
   - 不引入 SQLite、Redis、数据库迁移、ORM

3. 新的服务形态
   - 不改成 HTTP 服务
   - 不引入队列系统、任务系统、Worker 系统

4. 新的通知抽象
   - 不新增多渠道 notifier 架构

5. 复杂恢复机制
   - 不引入自动重试策略
   - 不引入告警系统
   - 不引入熔断、退避、重放框架

6. UI / 前端 / 可视化改造

7. 与本轮无关的代码整理
   - 大规模文件重组
   - 纯风格性批量改写

---

## 实现要求

### 1. 配置契约

1. 必须存在 `Settings` 单一配置入口。
2. `Settings` 必须负责：
   - 读取 `config.yaml`
   - 用 `PUSHER_WECOM_WEBHOOK` 覆盖 YAML 中 webhook
   - 在 live-run 时校验 webhook 格式
3. 采集器不得再自行读取 `config.yaml`。
4. `RssCollector` 必须接收注入的 `feed_configs`、`keywords`、`fetch_count`。
5. `HfDailyPapersCollector`、`TapTapCollector` 必须接收注入的 `fetch_count`。

### 2. 状态与事务契约

1. `pushed_urls.json` 文件结构保持为 `list[str]`，不得改成按 category 分组。
2. category 级推送成功后，必须立即提交：
   - `pushed_urls`
   - 当日 `{period}.json` 中对应 category 内容
3. category 级推送失败时：
   - 不得写入该 category 的 URL
   - 不得写入该 category 的日报内容
4. 已成功 category 的状态不得因后续失败丢失。
5. `StateStore` 写 JSON 必须使用原子替换方式。

### 3. 推送契约

1. `WeComPusher` 必须提供 `push_category()`。
2. `push_category()` 必须：
   - 校验 HTTP 状态
   - 校验业务 `errcode == 0`
3. 业务失败时必须抛出可识别异常，不能伪装成成功。

### 4. 运行结果契约

1. 任务结果必须区分：
   - 全成功
   - 部分失败
   - 全失败
2. 不允许把“部分失败”记录为“推送完成”并按纯成功语义结束。
3. `main.py` 必须根据实际 category 执行结果给出正确的最终日志结论和退出语义。

### 5. 锁契约

1. 必须存在单实例文件锁。
2. 锁必须在真正采集前获取。
3. 第二个实例拿不到锁时必须安全退出，不得继续执行采集或写状态。

### 6. 工程化契约

1. 必须提供 `pyproject.toml`。
2. 必须提供 `Makefile` 的统一入口。
3. 必须提供 CI，至少执行：
   - install
   - lint
   - test
4. README 必须与真实运行契约一致。
5. 如果 README 声明某种配置方式可用，代码必须真实支持；否则 README 必须改正。

---

## 验收标准

以下标准全部满足，当前任务才算通过：

### A. 配置

1. `main.py`、collectors 不再各自读取 `config.yaml`。
2. `RssCollector` 实际接收到 `Settings.rss_feeds`。
3. webhook 支持环境变量覆盖 YAML。

### B. 推送与状态

1. 某个 category 成功后，其 URL 会写入 `pushed_urls.json`。
2. 后续 category 失败时，前面已成功 category 的 URL 仍然保留。
3. 失败 category 的 URL 不会被写入。
4. category 级日报写入符合成功/失败结果。

### C. 结果语义

1. 全成功时，任务以成功语义结束。
2. 部分失败时，任务不得以“纯成功”语义结束。
3. 全失败时，任务不得以成功语义结束。

### D. 并发控制

1. 第二个实例拿不到锁时不会继续采集。

### E. 工程化

1. `make install` 可完成安装。
2. `make lint` 通过。
3. `make test` 通过。
4. CI 配置存在且与本地契约一致。

### F. 文档一致性

1. README 中的配置方式、运行方式、测试方式与真实代码行为一致。
2. 不允许 README 宣称 env-only 可用，而代码却强依赖 `config.yaml`。

---

## 测试命令

本轮 review 只认可以下测试命令及其结果：

```bash
make install
make lint
make test
make dry-run
```

关键定向测试应至少包含：

```bash
./venv/bin/pytest tests/test_settings.py -q
./venv/bin/pytest tests/test_state_store.py -q
./venv/bin/pytest tests/test_main.py -q
./venv/bin/pytest tests/test_wecom.py -q
./venv/bin/pytest tests/test_rss_collector.py -q
```

---

## Review Checklist

Review 只能逐项检查以下内容：

1. `Settings` 是否为单一配置入口
2. collectors 是否停止自行读配置
3. `rss_feeds` 是否真正注入 `RssCollector`
4. `push_category()` 是否校验 HTTP + `errcode`
5. category 成功后是否立即提交状态
6. category 失败后是否不污染状态
7. 部分失败是否仍被错误标记为整体成功
8. 锁是否阻止第二实例继续执行
9. `make install/lint/test/dry-run` 是否成立
10. README 是否与真实行为一致

只有上述 checklist 失败，才能作为阻塞项。

---

## 非本轮范围

以下内容如果在 review 阶段被发现，只能进入 `next_task`，不得阻塞当前任务：

1. SQLite 替代 JSON
2. 自动重试
3. 告警系统
4. 结构化指标上报
5. 多通知渠道抽象
6. HTTP API 化
7. 更复杂的 lock 可视化/续租机制
8. 数据源注册中心
9. 更细粒度异常分流
10. 更激进的目录重构
11. 性能微优化
12. 非本轮必须的类型系统增强

---

## 审查记录

| 轮次 | 结论 | 归档 |
|---|---|---|
| 初审 | 不通过（3 阻塞项） | `docs/superpowers/specs/2026-05-16-m1-m2-implementation-code-review-report.md` |
| 二审 | 不通过（2 阻塞项） | `docs/superpowers/specs/2026-05-16-m1-m2-final-review-report.md` |
| 终审 | **通过** | `spec/task001/spec.md`（本文件） |

通过时验证：73 passed, lint zero, `make install/lint/test/dry-run` 全部成立。

## next_task

后续新发现但不属于本轮范围的问题：

### M3 可维护性重构

1. 从 `main.py` 抽取 `digest_service.py`
2. collector registry 机制
3. `push()` 兼容包装移除，统一为 `push_category()`
4. `FEED_CONFIGS` 硬编码迁移到配置

### M4 生产化增强

5. SQLite 替代 JSON 状态存储
6. 结构化日志
7. 推送失败告警
8. Docker 化交付

### 其他

9. 文档清理：收敛 `docs/superpowers/` 中本轮过程性文件
10. env-only 启动支持：当前强依赖 `config.yaml`，如需纯环境变量启动需独立设计
11. 并发锁行为测试补强
