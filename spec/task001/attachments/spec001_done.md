# Claw_news M1+M2 Task Contract Spec — ~~DONE~~

> **状态: 已完成** | 通过验证: 73 passed, lint zero | 提交: `22b5d20`

## ~~Immutable Rule~~

~~本文件是当前任务的唯一验收契约。~~
~~自确认后：~~

1. ~~Review 只能基于本文件判断是否通过。~~
2. ~~Review 不允许提出新的范围外阻塞项。~~
3. ~~新发现但不属于本文件范围的问题，必须记录到 `next_task`，不得阻塞当前任务。~~
4. ~~阻塞项必须能映射到本文件的”实现要求”或”验收标准”。~~
5. ~~禁止使用”建议优化””最好””可以考虑”作为阻塞理由。~~

---

## ~~任务目标~~

~~在不改变现有热点评分逻辑、分类逻辑、消息格式核心语义的前提下，完成 M1/M2 工程化改造，使项目达到以下目标：~~

1. ~~配置加载有单一入口，支持环境变量覆盖 webhook。~~
2. ~~推送按 category 独立提交状态，已成功 category 的状态不会因后续失败而丢失。~~
3. ~~企业微信响应同时校验 HTTP 状态和业务 `errcode`。~~
4. ~~任务运行具备单实例锁，避免并发重入。~~
5. ~~项目具备统一安装、测试、lint、CI 入口。~~
6. ~~文档与真实运行契约一致。~~

---

## ~~修改范围~~

~~本轮允许修改以下内容：~~

1. ~~运行编排层 — `main.py`~~
2. ~~配置与状态边界 — `infra/`~~
3. ~~推送层 — `pusher/wecom.py`~~
4. ~~采集器配置注入 — `collectors/`~~
5. ~~测试 — `tests/`~~
6. ~~工程化文件 — `pyproject.toml`, `Makefile`, CI~~
7. ~~文档与部署 — `README.md`, `deploy.example.sh`~~

---

## ~~禁止修改范围~~

~~本轮禁止：评分逻辑重构、新存储方案、新服务形态、新通知抽象、复杂恢复机制、UI改造、无关代码整理~~

---

## ~~实现要求~~

### ~~1. 配置契约~~
1. ~~`Settings` 单一配置入口~~
2. ~~环境变量覆盖 YAML webhook~~
3. ~~采集器不得自行读 `config.yaml`~~
4. ~~`RssCollector` 注入 `feed_configs`/`keywords`/`fetch_count`~~
5. ~~`HfDailyPapersCollector`/`TapTapCollector` 注入 `fetch_count`~~

### ~~2. 状态与事务契约~~
1. ~~`pushed_urls.json` 保持 `list[str]`~~
2. ~~category 成功后立即提交状态~~
3. ~~category 失败不污染状态~~
4. ~~已成功状态不因后续失败丢失~~
5. ~~`StateStore` 原子替换写入~~

### ~~3. 推送契约~~
1. ~~`push_category()` 校验 HTTP + errcode~~
2. ~~业务失败抛可识别异常~~

### ~~4. 运行结果契约~~
1. ~~区分全成功/部分失败/全失败~~
2. ~~不允许部分失败标记为”推送完成”~~
3. ~~正确退出语义~~

### ~~5. 锁契约~~
1. ~~单实例文件锁~~
2. ~~锁在采集前获取~~
3. ~~第二实例拿不到锁安全退出~~

### ~~6. 工程化契约~~
1. ~~`pyproject.toml` + `Makefile` + CI~~
2. ~~README 与真实行为一致~~

---

## ~~验收标准 A-F~~

~~全部满足：配置、推送与状态、结果语义、并发控制、工程化、文档一致性。~~

---

## ~~Review Checklist~~

1. ~~Settings 单一配置入口~~
2. ~~collectors 停止自行读配置~~
3. ~~rss_feeds 真正注入 RssCollector~~
4. ~~push_category() 校验 HTTP + errcode~~
5. ~~category 成功后立即提交状态~~
6. ~~category 失败后不污染状态~~
7. ~~部分失败不标记为整体成功~~
8. ~~锁阻止第二实例~~
9. ~~make install/lint/test/dry-run 成立~~
10. ~~README 与真实行为一致~~

---

## 审查记录

| 轮次 | 结论 | 归档 |
|---|---|---|
| 初审 | 不通过（3 阻塞项） | `docs/superpowers/specs/2026-05-16-m1-m2-implementation-code-review-report.md` |
| 二审 | 不通过（2 阻塞项） | `docs/superpowers/specs/2026-05-16-m1-m2-final-review-report.md` |
| 终审 | **通过** | `spec/task001/attachments/spec001_done.md`（本文件） |

通过时验证：73 passed, lint zero, `make install/lint/test/dry-run` 全部成立。

## next_task → 已迁移至 `spec/task002/attachments/spec.md`
