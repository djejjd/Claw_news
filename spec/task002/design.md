# Task002 Design

## 本轮目标

一句话版本：

在已有正确性和工程化基础上，继续清理兼容包装、配置硬编码和过程性文档，提升可维护性。

详细目标：

1. 让 `push_category()` 成为唯一推送入口
2. 让 RSS 源配置不再硬编码在代码里
3. 让 `docs/superpowers/` 中的历史过程文档得到收敛

## 设计结论

1. Task002 本质是 M3 可维护性重构
2. 该任务不引入新服务形态、不扩展新存储、不改评分逻辑
3. 重点是删除兼容层、迁移硬编码、清理文档债务

## 详细设计来源

- [docs/architecture/roadmap/m1-m4-optimization-roadmap.md](/Users/lanser/Code/Claw_news/docs/architecture/roadmap/m1-m4-optimization-roadmap.md)
