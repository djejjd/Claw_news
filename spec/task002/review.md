# Task002 Review

## 本轮目标

为 Task002 预留统一评审入口，并说明当前历史材料状态。

## 当前状态

1. 当前仓库中未见与 Task002 一一对应的正式 review 归档入口
2. 结合当前项目代码状态，Task002 不应视为已完成

## 当前核实结果

按 Task002 原始目标与当前项目状态核实，至少存在以下未完成项：

1. `WeComPusher.push()` 兼容包装仍然存在
   - 见 [pusher/wecom.py](/Users/lanser/Code/Claw_news/pusher/wecom.py:161)
2. 测试仍在调用 `push()`
   - 见 [tests/test_wecom.py](/Users/lanser/Code/Claw_news/tests/test_wecom.py:111)
3. `collectors/rss_sources.py` 中 `FEED_CONFIGS` 仍然存在
   - 见 [collectors/rss_sources.py](/Users/lanser/Code/Claw_news/collectors/rss_sources.py:10)

因此本任务当前结论是：

1. 不能补成完成态
2. 也不适合直接并入 Task004

## 是否并入最新 task 的评估

不建议整体并入最新 task，原因：

1. Task002 的核心是旧 CLI 可维护性重构
2. Task004 的核心是 AI 助手服务交付完善
3. 两者目标、影响文件和验收边界都不同，强行合并会让 Task004 范围失真

更合理的处理方式：

1. `push()` 移除与 `FEED_CONFIGS` 迁移
   - 保留为独立 backlog task
2. “过程性文档收敛”这一小部分
   - 可并入 Task005 的目录治理范围统一处理

## 评审基线

1. Task002 的正式评审应只对 [contract.md](/Users/lanser/Code/Claw_news/spec/task002/contract.md) 负责
2. 当前迁移期如需看完整条款，读取 [attachments/spec.md](/Users/lanser/Code/Claw_news/spec/task002/attachments/spec.md)
