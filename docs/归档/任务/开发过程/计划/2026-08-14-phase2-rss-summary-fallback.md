# Phase 2 RSS 摘要字段兼容修复

**任务编号：** CG-P2-FIX-01  
**依赖任务：** CG-P2-02（`593c42a`）  
**允许并行任务：** 无  
**预计修改文件：** `collectors/rss_sources.py`、`tests/test_rss_collector.py`、本任务记录  
**不得修改文件：** 来源策略、分类规则、选材算法、推送协议、真实运行配置  
**完成状态：** in_progress

## 1. 背景

服务器验证显示 Hugging Face Blog RSS 可连通并解析出 10 条内容，但其条目使用 `description`/`content` 而非 `summary`，被候选准入的最小摘要长度规则全部拒绝。

## 2. 目标

让 RSS 解析器在 `summary` 缺失或为空时按 `description`、`content` 回退，令符合既有准入规则的公开 RSS 条目进入候选池。

## 3. 前置依赖

Phase 2 来源扩展和服务器实测结果；不改变其来源、分类和策略契约。

## 4. 输入与输出契约

输入为 feedparser 条目。输出摘要优先级固定为 `summary -> description -> content -> title`，经 HTML 清理后写入 `HotItem.summary`；仅标题可用的 feed 以标题作为最小可解释摘要。

## 5. 修改范围

仅修改 RSS 条目摘要提取与单元测试，并记录任务执行状态。

## 6. 禁止事项

不得放宽摘要最小长度、不得为单一来源硬编码、不得改写存量候选或触发额外推送。

## 7. 执行要求

测试先行：先添加 `description` 与 `content` 的失败用例，再实现最小回退逻辑；完成后运行 RSS 精确测试、全量测试、lint、format 与 diff 检查，并进行独立只读审核。

## 8. 实施步骤

- [ ] 添加 RSS 摘要回退失败测试。
- [ ] 实现通用字段回退并保持 HTML 清理。
- [ ] 运行本地检查与独立代码审核。
- [ ] 获得用户部署授权后重新部署，并进行无推送采集验证。

## 9. 验收标准

1. `summary` 仍优先于其他字段。
2. 无 `summary` 的 `description` 和 `content` 可生成非空摘要。
3. 三字段均为空时保持空摘要。
4. Hugging Face Blog 在服务器采集后可进入候选池。

## 10. 检查命令

```bash
./venv/bin/pytest tests/test_rss_collector.py -v
./venv/bin/pytest -v
./venv/bin/ruff check .
./venv/bin/ruff format --check .
git diff --check
```

## 11. 交付前自检

- [ ] 已确认仅修改允许范围。
- [ ] 已覆盖正常、优先级和空字段边界。
- [ ] 未改变来源策略、分类、评分或推送语义。
- [ ] 已完成独立审核与部署验证。

## 12. 交付格式

按 `AGENTS.md` 固定十段格式交付，说明测试、独立审核、部署结果和残留风险；未经用户授权不得发送额外消息。
