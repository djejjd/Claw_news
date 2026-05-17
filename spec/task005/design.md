# Task005 Design

## 本轮目标

一句话版本：

把 task 文档目录从“能用”整理到“长期稳定可维护”。

详细目标：

1. 统一每个 task 的正式入口结构
2. 统一“本轮目标”的固定落点
3. 区分正式入口、共享模板和历史原件
4. 让 review 以后只对 `contract.md` 负责

## 设计结论

1. `spec/taskNNN/` 是每个任务的唯一正式目录
2. 正式文档固定为 `contract/design/plan/review/done`
3. `attachments/` 用于承载历史原件和补充材料
4. `spec/meta/` 用于承载跨任务复用的角色与模板
5. `docs/tasks/`、`docs/architecture/`、`docs/operations/` 按职责分层，不再使用 `docs/superpowers/*` 作为正式入口

## 详细设计来源

- [docs/tasks/task005/design.md](/Users/lanser/Code/Claw_news/docs/tasks/task005/design.md)
