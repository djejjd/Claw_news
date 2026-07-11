# Claw_news Agent Development Contract

本文件是所有开发 AI 的仓库级公共契约。共享规则只在此维护；工具专属文件只能补充适配说明，不得复制或改写公共规则。

## 必读顺序

开始任何工作前，依次完整阅读：

1. 用户当前指令与当前任务包；
2. 任务包指定的已批准设计章节；
3. 本文件；
4. 对应工具的专属补充文件；
5. `README.md`、`docs/CONVENTIONS.md` 以及任务相关的稳定文档和现有代码。

## 指令优先级

```text
用户当前指令
> 当前任务包
> 已批准设计文档
> AGENTS.md
> CLAUDE.md 中的工具专属补充
> 历史代码注释与归档文档
```

若较低优先级内容与较高优先级内容冲突，以较高优先级为准；满足“强制停止条件”时不得自行裁决后继续实现。

## 强制门禁

以下规则每次修改前必须逐条确认，不可跳过：

1. **中文文档优先**：仓库内设计、计划、开发说明和变更说明默认使用中文；英文只能作为补充，代码标识符、命令和协议字段保持原文。
2. **分支隔离**：任何修改前必须确认不在 `main` 分支；如果在 `main`，必须先创建并切换到新分支，简单修复也不例外。
3. **工作区评估**：多文件改动、功能开发或需要多轮 review 的迭代工作，默认先评估是否应使用独立 worktree 或隔离工作区，不在主工作区长期叠加修改。
4. **任务级 commit 审核**：任何 `git commit` 前，必须先完整检查并向主审核 AI 展示 `git diff`，取得主审核 AI 的明确批准后方可提交；任务包不得以“自行检查 diff”为由绕过该审核。用户可直接批准某次 commit，但不是任务级 commit 的必经审批人。
5. **最终集成与外部操作审核**：任何最终 `merge`、`git push` 或 `deploy` 都必须获得用户明确同意，不因改动简单或明显而跳过；主审核 AI 批准任务级 commit 不等于用户批准最终集成、推送或部署。

## 架构与稳定文档入口

- 快速上手：`README.md`
- 文档规范：`docs/CONVENTIONS.md`
- 公开提交边界：`docs/PUBLICATION_POLICY.md`
- 部署指南：`docs/operations/deploy/server-guide.md`
- 长期架构：`docs/architecture/`
- 历史探索：`docs/archive/`，不作为当前实现依据

当前主流程由 `main.py` 编排，数据沿 Collectors → Aggregator → Pusher 流动：

- `collectors/base.py` 定义统一数据对象 `HotItem`；各异步 collector 返回 `List[HotItem]`，由 `safe_collect()` 隔离单源失败。
- `aggregator/` 中的 `Merger.merge()` 负责去重、评分、来源保底、开放竞争和分类截断。
- `pusher/` 中的 `WeComPusher` 负责企微 markdown 格式化与推送。
- `config/settings.py` 负责配置加载与校验；`storage/state_store.py` 负责跨次去重和日报原子落盘。
- `main.py` 负责加载配置、文件锁、采集、合并、推送或 dry-run，以及逐分类状态持久化。

关键约定：`config.yaml` 和 `data/` 不入库；示例配置使用 `config.example.yaml`；测试通过可注入 HTTP client 避免网络；需要 TLS 指纹时使用 `curl-cffi`，企微 webhook 使用 `httpx`。

## 常用检查命令

所有命令使用 `make install` 创建的虚拟环境：

```bash
make install       # 创建 venv 并安装 editable package 与开发依赖
make test          # 运行全部测试：pytest -v
make lint          # Ruff lint 检查
make format        # Ruff 格式化
make dry-run       # 不推送的早间流程，打印格式化结果
make run-morning   # 完整早间流程：collect → score → push
make run-evening   # 完整晚间流程
```

单测示例：

```bash
./venv/bin/pytest tests/test_merger.py::test_function_name -v
```

CI 使用 Python 3.12（本地支持 Python 3.11+），依次运行 `pip install -e ".[dev]"`、`ruff format --check`、`ruff check` 和 `pytest -v`。

## 任务执行规则

每个实施 Task 必须标明任务编号、依赖任务、允许并行任务、预计修改文件、不得修改文件和完成状态，并包含以下十二段：

1. 背景；
2. 目标；
3. 前置依赖；
4. 输入与输出契约；
5. 修改范围；
6. 禁止事项；
7. 执行要求；
8. 实施步骤；
9. 验收标准；
10. 检查命令；
11. 交付前自检；
12. 交付格式。

严格按依赖顺序和文件边界执行。代码 Task 必须测试先行：先看到新测试按预期失败，再写最小实现。新想法默认记录为后续项，不在当前 Task 顺手扩展。每个 Task 只提交自己的范围，任务内未明确授权时不得 commit，任何情况下不得未经用户批准 push。

## 强制停止条件

若任务包、批准设计、现有代码三者存在无法兼容的冲突，立即停止实现，报告冲突位置、影响和可选处理方案；不得自行扩大范围、修改契约或用静默兼容掩盖冲突。

## 交付前自检

交付前必须逐项确认：

1. 已完整阅读 `AGENTS.md`、任务包和任务指定设计章节；
2. 只修改了允许范围；
3. 没有擅自改变接口、状态语义、默认值或评分常量；
4. 新行为具备正常、边界、降级和失败路径测试；
5. 没有静默 fallback、吞异常或伪成功；
6. 可配置规则没有被重新硬编码到业务逻辑；
7. 旧配置兼容行为符合任务包；
8. 示例配置和中文文档已同步；
9. 已运行任务包指定的精确测试；
10. 已运行要求的完整测试、lint 和格式检查；
11. 已检查 diff 中的意外修改、调试代码、密钥和机器绝对路径；
12. 每条验收标准都有对应证据；
13. 未验证内容明确标记，未被描述为已完成。

不适用于纯文档 Task 的代码测试项，应在交付中明确标记为“不适用”，不得伪造测试结果。

## 固定交付格式

每个开发 AI 必须按以下结构交付：

1. 完成内容；
2. 实际修改文件；
3. 与设计契约的逐条对应；
4. 执行的检查命令及结果；
5. 新增或修改的测试；
6. 未完成项；
7. 残留风险；
8. 发现的设计冲突；
9. 范围外改动声明；
10. 建议主审核 AI 重点检查的位置。
