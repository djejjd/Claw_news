# Task003 Contract

## 任务目标

在不破坏现有 `Claw_news` 热点聚合 CLI 流程的前提下，为当前仓库新增一个可独立运行的服务化 MVP：

1. 支持按配置抓取 RSS 新闻
2. 调用 OpenAI-compatible 模型生成中文摘要分析
3. 将摘要结果推送到企业微信群机器人
4. 提供 `FastAPI` HTTP 接口用于健康检查与手动触发
5. 提供 `APScheduler` 定时任务用于自动运行
6. 提供 `Dockerfile` 与 `docker-compose.yml` 用于 Linux 服务器部署

## 当前状态

1. 本任务已完成
2. 本任务最终 review 结论为 `PASS`
3. 本文件作为 Task003 在新目录规范下的正式契约入口

## 正式契约入口

Task003 的完整正式契约内容仍以历史契约原文为准：

- [attachments/spec.md](/Users/lanser/Code/Claw_news/spec/task003/attachments/spec.md)

当前迁移阶段约定：

1. 开发和 review 在定位 Task003 范围时，先从本文件进入
2. 需要完整实现要求、验收标准、Review Checklist 时，读取 `spec/task003/attachments/spec.md`
3. 后续如果执行二次整理，再将 `spec.md` 内容完整收拢到本文件

## 文档入口

- 设计：[design.md](/Users/lanser/Code/Claw_news/spec/task003/design.md)
- 计划：[plan.md](/Users/lanser/Code/Claw_news/spec/task003/plan.md)
- 评审：[review.md](/Users/lanser/Code/Claw_news/spec/task003/review.md)
- 归档：[done.md](/Users/lanser/Code/Claw_news/spec/task003/done.md)

## 历史文件

- 原契约：[attachments/spec.md](/Users/lanser/Code/Claw_news/spec/task003/attachments/spec.md)
- 原评审报告：[attachments/review_report.md](/Users/lanser/Code/Claw_news/spec/task003/attachments/review_report.md)
- 代码实现说明：[attachments/ds_code.md](/Users/lanser/Code/Claw_news/spec/task003/attachments/ds_code.md)
