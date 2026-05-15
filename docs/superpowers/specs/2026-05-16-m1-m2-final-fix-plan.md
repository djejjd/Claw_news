# Claw_news M1+M2 终审修复方案

> 对应终审报告: `docs/superpowers/specs/2026-05-16-m1-m2-final-review-report.md`
> 状态: 方案已定，待执行

## 修改摘要

终审 2 个阻塞项 + 3 个建议项一并修复：

| # | 来源 | 问题 | 修改 |
|---|---|---|---|
| 1 | 3.1 | 部分失败仍以成功退出 | `run_push_sequence()` 返回 `dict` 汇总成功/失败 category；`main()` 根据结果决定日志结论并设置退出码 |
| 2 | 3.2 | README 与实现的配置契约不一致 | 方案 B：收紧 README，明确 `config.yaml` 必须存在，环境变量只覆盖 webhook |
| 3 | 4.1 | 异常处理未向上返回结构化结果 | 与 3.1 合并 |
| 4 | 4.2 | 缺配置契约测试 | `test_load_raises_when_config_yaml_missing` |
| 5 | 4.3 | 缺部分失败退出语义测试 | `test_run_push_sequence_returns_failure_summary` + `test_run_push_sequence_all_success` |

## 3.2 方案选择理由

选 **方案 B（改文档）** 而非方案 A（改代码支持 env-only）：

- M1/M2 的核心目标是消除状态不一致和隐式配置，不是增加新的配置方式
- `config.yaml` 还承载 `fetch_count`、`top_n`、`keywords`、`rss_feeds` 等多个必填字段，仅靠 env var 无法替代
- 方案 B 零代码改动，零风险
- 如需 env-only 支持，应在 M4 中作为独立需求设计

## 修改文件

```
main.py                    — 3.1/4.1: run_push_sequence() 返回汇总结果，main() 退出码
tests/test_main.py         — 4.3: 补部分失败 + 全成功退出语义测试
tests/test_settings.py     — 4.2: 补 config.yaml 缺失测试
README.md                  — 3.2: 收紧配置契约
```

## Patch

### main.py — run_push_sequence() 返回汇总结果

返回值从 `set[str]`（仅 pushed_urls）改为 `dict`（含 success/failed 汇总）：

```python
async def run_push_sequence(grouped, period, pushed_urls, state_store, pusher):
    current_urls = set(pushed_urls)
    success_categories: list[str] = []
    failed_categories: list[str] = []

    for category in ("ai", "game", "device"):
        cat_items = grouped.get(category, [])
        if not cat_items:
            continue

        try:
            result = await pusher.push_category(
                category=category, items=cat_items,
                period=period, pushed_urls=current_urls,
            )
        except Exception as exc:
            logger.error("push failed for category=%s: %s", category, exc)
            failed_categories.append(category)
            continue

        if result.success:
            current_urls = state_store.merge_pushed_urls(set(result.urls))
            state_store.write_daily_digest_category(
                period=period, category=category,
                items=[{"title": i.title, "url": i.url, "summary": i.summary,
                        "source": i.source, "score": i.source_score}
                       for i in cat_items],
            )
            success_categories.append(category)
        else:
            logger.error(
                "push failed for category=%s errcode=%s errmsg=%s",
                result.category, result.errcode, result.errmsg,
            )
            failed_categories.append(category)

    return {
        "pushed_urls": current_urls,
        "success_categories": success_categories,
        "failed_categories": failed_categories,
    }
```

### main.py — main() 根据结果决定退出语义

```python
# 替换现有 push 段:
summary = await run_push_sequence(
    grouped=grouped, period=period,
    pushed_urls=pushed_urls, state_store=state_store, pusher=pusher,
)
cleanup_old_digests()

failed = summary["failed_categories"]
success = summary["success_categories"]

if not success and failed:
    logger.error("推送全部失败 (%s)", ", ".join(failed))
    sys.exit(1)
elif failed:
    logger.error("部分推送失败 — 成功: %s, 失败: %s",
                 ", ".join(success), ", ".join(failed))
    sys.exit(1)
else:
    logger.info("推送完成")
```

### tests/test_main.py — 补退出语义测试

```python
@pytest.mark.asyncio
async def test_run_push_sequence_returns_failure_summary(tmp_path: Path):
    """部分失败时返回的汇总包含正确的 success/failed 列表"""
    from infra.storage.state_store import StateStore
    from main import run_push_sequence

    grouped = {
        "ai": [HotItem("AI", "https://a.com/1", "", "qbitai", "ai", 5.0)],
        "game": [HotItem("Game", "https://g.com/1", "", "yystv", "game", 5.0)],
        "device": [HotItem("Device", "https://d.com/1", "", "ithome", "device", 5.0)],
    }
    store = StateStore(tmp_path)

    summary = await run_push_sequence(
        grouped=grouped, period="morning",
        pushed_urls=store.load_pushed_urls(),
        state_store=store,
        pusher=RaisingStubPusher(fail_category="device"),
    )

    assert summary["success_categories"] == ["ai", "game"]
    assert summary["failed_categories"] == ["device"]
    assert "https://a.com/1" in summary["pushed_urls"]
    assert "https://g.com/1" in summary["pushed_urls"]
    assert "https://d.com/1" not in summary["pushed_urls"]


@pytest.mark.asyncio
async def test_run_push_sequence_all_success(tmp_path: Path):
    """全成功时返回空 failed 列表"""
    from infra.storage.state_store import StateStore
    from main import run_push_sequence

    grouped = {
        "ai": [HotItem("AI", "https://a.com/1", "", "qbitai", "ai", 5.0)],
    }
    store = StateStore(tmp_path)

    summary = await run_push_sequence(
        grouped=grouped, period="morning",
        pushed_urls=store.load_pushed_urls(),
        state_store=store,
        pusher=StubPusher(),
    )

    assert summary["success_categories"] == ["ai"]
    assert summary["failed_categories"] == []
```

### tests/test_settings.py — 补配置契约测试

```python
def test_load_raises_when_config_yaml_missing(tmp_path: Path):
    """config.yaml 缺失时必须抛出明确错误"""
    config_path = tmp_path / "nonexistent.yaml"
    with pytest.raises(ValueError, match="config file not found"):
        Settings.load(config_path)
```

### README.md — 收紧配置契约

```markdown
# 2. 配置 webhook
#    首先必须有 config.yaml（从模板复制）:
cp config.example.yaml config.yaml
#    然后配置 webhook（二选一）:
#    方式 A: 环境变量（推荐，覆盖 YAML 中的 webhook）
export PUSHER_WECOM_WEBHOOK="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY_HERE"
#    方式 B: 直接在 config.yaml 中填写 webhook
```

## 测试命令

```bash
source venv/bin/activate
python -m pytest tests/test_main.py tests/test_settings.py -v  # 新增测试
python -m pytest tests/ -q  # 全量回归（预期 73 passed）
ruff check .
```

## 风险说明

- **3.1 退出码变更**: 之前所有非异常退出都是 0，现在部分失败或全失败会退出 1。需确认 launchd/cron 对退出码无特殊依赖。正常全成功路径行为不变。
- **run_push_sequence 返回值变更**: 原返回 `set[str]`，现返回 `dict`。唯一调用方是 `main()` 自身，无外部消费者。
- **README 契约收紧**: 纯文档修改，零代码影响。
- **现有测试兼容**: 旧测试调用 `run_push_sequence()` 但未检查返回值（直接丢弃），无需修改。新增测试覆盖新语义。
