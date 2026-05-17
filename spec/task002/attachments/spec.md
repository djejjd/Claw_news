# Claw_news M3 Task Contract Spec

## Immutable Rule

本文件是当前任务的唯一验收契约。
自确认后：

1. Review 只能基于本文件判断是否通过。
2. Review 不允许提出新的范围外阻塞项。
3. 新发现但不属于本文件范围的问题，必须记录到 `next_task`，不得阻塞当前任务。
4. 阻塞项必须能映射到本文件的"实现要求"或"验收标准"。
5. 禁止使用"建议优化""最好""可以考虑"作为阻塞理由。

---

## 任务目标

在 M1/M2 已建立的工程化基础上，完成 M3 可维护性重构：

1. ~~`main.py` 职责收敛~~ → 上一轮已完成
2. `push()` 兼容包装移除，统一为 `push_category()`
3. `FEED_CONFIGS` 硬编码迁移到配置
4. collector registry 机制（可选，视复杂度决定）
5. `docs/superpowers/` 中过程性文件收敛清理

---

## 修改范围

本轮允许修改以下内容：

1. 推送层
   - `pusher/wecom.py` — 移除 `push()` 兼容包装

2. 配置与采集器
   - `collectors/rss_sources.py` — `FEED_CONFIGS` 迁移
   - `config.example.yaml` — 补充 `rss_feeds` 默认值

3. 编排层
   - `main.py` — 调整调用方（移除 `push()` 调用，确认 `push_category()` 为唯一入口）

4. 测试
   - `tests/test_wecom.py` — 移除 `push()` 相关测试，保留 `push_category()` 测试
   - 为兼容本轮改动而必要调整的现有测试文件

5. 文档
   - 收敛 `docs/superpowers/` 中本轮已不需要的过程性文件
   - 将保留文件归入合理的子目录结构

---

## 禁止修改范围

本轮禁止：

1. 评分逻辑 — `aggregator/merger.py`、`collectors/base.py`
2. 新存储方案 — 不引入 SQLite、Redis
3. 新服务形态 — 不改成 HTTP 服务
4. 新通知抽象 — 不新增多渠道 notifier
5. 复杂恢复机制 — 不引入自动重试、告警
6. 采集器业务逻辑 — `huggingface.py`、`taptap.py` 的采集/解析代码
7. `StateStore` 接口变更
8. `Settings` 接口变更

---

## 实现要求

### 1. push() 移除

1. `WeComPusher.push()` 兼容包装必须删除。
2. `main.py` 中调用方已使用 `push_category()`（M1/M2 已完成），确认无残留 `push()` 调用。
3. 测试中残留的 `push()` 调用必须改为 `push_category()` 或删除。

### 2. FEED_CONFIGS 迁移

1. `collectors/rss_sources.py` 中 `FEED_CONFIGS` 硬编码列表迁移到 `config.example.yaml` 的 `rss_feeds` 字段。
2. `RssCollector` 不再有硬编码默认值；启动时若 `settings.rss_feeds` 为空则打印 warning 但不崩溃（RSS 源为空合理）。
3. `config.example.yaml` 的 `rss_feeds` 包含当前 4 个源的完整配置。

### 3. 文档收敛

1. `docs/superpowers/specs/` 中与 M1/M2 强相关的过程性文件归档或删除。
2. 设计文档与实施计划保留，review 报告可合并或删除。

---

## 验收标准

### A. push() 已移除

1. `pusher/wecom.py` 中不存在 `async def push(self, items_by_category, ...)` 方法。
2. 全项目 `grep -r "\.push("` 无对 `WeComPusher.push()` 的调用。
3. 现有 `push_category()` 测试全部通过。

### B. FEED_CONFIGS 已迁移

1. `collectors/rss_sources.py` 中不存在 `FEED_CONFIGS` 常量。
2. `config.example.yaml` 中 `rss_feeds` 字段包含 4 个源。
3. 未配置 `rss_feeds` 时 RSS 采集器不崩溃。

### C. 文档已收敛

1. `docs/superpowers/` 中无冗余过程性文件。

### D. 无回归

1. `make test` 全部通过。
2. `make lint` 通过。
3. `make dry-run` 正常执行。

---

## 测试命令

```bash
make lint
make test
make dry-run
grep -r "\.push(" main.py pusher/ tests/  # 确认无残留
grep "FEED_CONFIGS" collectors/rss_sources.py  # 确认已删除
```

---

## Review Checklist

1. `push()` 方法是否已删除
2. 全项目是否无 `WeComPusher.push()` 调用
3. `FEED_CONFIGS` 是否已从代码中移除
4. `config.example.yaml` 是否包含 `rss_feeds`
5. 无 `rss_feeds` 配置时 RSS 采集是否不崩溃
6. `docs/superpowers/` 是否已收敛
7. `make lint/test/dry-run` 是否全部通过

---

## 非本轮范围

以下内容只能进入 `next_task`，不得阻塞当前任务：

1. SQLite 替代 JSON
2. 自动重试
3. 告警系统
4. Docker 化
5. collector registry
6. HTTP API 化
7. env-only 启动支持

---

## next_task

（预留）
