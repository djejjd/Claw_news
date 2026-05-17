# Task001 Contract

## 任务目标

在不改变现有热点评分逻辑、分类逻辑、消息格式核心语义的前提下，完成 M1/M2 工程化改造，使项目达到以下目标：

1. 配置加载有单一入口，支持环境变量覆盖 webhook
2. 推送按 category 独立提交状态，已成功 category 的状态不会因后续失败而丢失
3. 企业微信响应同时校验 HTTP 状态和业务 `errcode`
4. 任务运行具备单实例锁，避免并发重入
5. 项目具备统一安装、测试、lint、CI 入口
6. 文档与真实运行契约一致

## 当前状态

1. 本任务已完成
2. 本文件作为 Task001 在新目录规范下的正式契约入口

## 正式契约入口

Task001 当前没有独立保留的“未完成态 contract 原文”，现阶段以完成归档原文作为正式契约来源：

- [attachments/spec001_done.md](/Users/lanser/Code/Claw_news/spec/task001/attachments/spec001_done.md)

当前迁移阶段约定：

1. 开发和 review 追溯 Task001 范围时，先从本文件进入
2. 需要完整历史条款和审查记录时，读取 `spec/task001/attachments/spec001_done.md`

## 文档入口

- 设计：[design.md](/Users/lanser/Code/Claw_news/spec/task001/design.md)
- 计划：[plan.md](/Users/lanser/Code/Claw_news/spec/task001/plan.md)
- 评审：[review.md](/Users/lanser/Code/Claw_news/spec/task001/review.md)
- 归档：[done.md](/Users/lanser/Code/Claw_news/spec/task001/done.md)
