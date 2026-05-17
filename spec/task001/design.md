# Task001 Design

## 本轮目标

一句话版本：

完成 M1/M2 工程化改造，先解决正确性与工程基础，再为后续 M3/M4 演进打底。

详细目标：

1. 收敛配置边界，避免采集器和推送逻辑散读配置
2. 修正 category 级状态提交和企微错误识别
3. 增加任务锁、统一测试命令和 CI
4. 保持原有热点评分和消息核心语义不被破坏

## 设计结论

1. M1 聚焦安全与正确性，不做大重构
2. M2 聚焦工程化基础，补齐 `pyproject.toml`、`Makefile`、CI、README
3. 所有变更都以“修边界、保语义”为原则

## 详细设计来源

- [docs/tasks/task001/design.md](/Users/lanser/Code/Claw_news/docs/tasks/task001/design.md)
- [docs/architecture/roadmap/m1-m4-optimization-roadmap.md](/Users/lanser/Code/Claw_news/docs/architecture/roadmap/m1-m4-optimization-roadmap.md)
