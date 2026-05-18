# Tasks Index

本目录用于承载每一轮任务的正式文档入口。

目录治理规则：

1. 每个任务的正式入口目录为 `spec/taskNNN/`
2. 正式契约文件固定命名为 `contract.md`
3. 设计文档固定命名为 `design.md`
4. 实施计划固定命名为 `plan.md`
5. 评审结论固定命名为 `review.md`
6. 完成归档固定命名为 `done.md`
7. 每个 task 都必须清晰写出“本轮目标”

当前仓库仍处于迁移期：

1. 历史文件暂时保留
2. 新入口文件优先用于定位和阅读
3. review 规则最终只对 `contract.md` 负责

## 共享角色与模板

以下内容不是某一轮 task 的业务交付物，而是跨任务复用的角色划定与审查模板：

- 索引：[spec/meta/README.md](/Users/lanser/Code/Claw_news/spec/meta/README.md)
- 开发执行者角色：[spec/meta/developer-role.md](/Users/lanser/Code/Claw_news/spec/meta/developer-role.md)
- 契约生成模板：[spec/meta/spec-author-template.md](/Users/lanser/Code/Claw_news/spec/meta/spec-author-template.md)
- Review 模板：[spec/meta/review-template.md](/Users/lanser/Code/Claw_news/spec/meta/review-template.md)

## task001

状态：已完成

目标：完成 M1/M2 工程化改造，统一配置入口、修正推送与状态提交语义、增加单实例锁，并补齐测试与 CI。

正式入口：
- 契约：[spec/task001/contract.md](/Users/lanser/Code/Claw_news/spec/task001/contract.md)
- 设计：[spec/task001/design.md](/Users/lanser/Code/Claw_news/spec/task001/design.md)
- 计划：[spec/task001/plan.md](/Users/lanser/Code/Claw_news/spec/task001/plan.md)
- 评审：[spec/task001/review.md](/Users/lanser/Code/Claw_news/spec/task001/review.md)
- 归档：[spec/task001/done.md](/Users/lanser/Code/Claw_news/spec/task001/done.md)

历史来源：
- 原完成归档：[spec/task001/attachments/spec001_done.md](/Users/lanser/Code/Claw_news/spec/task001/attachments/spec001_done.md)
- 共享角色模板已迁出至：[spec/meta/README.md](/Users/lanser/Code/Claw_news/spec/meta/README.md)

## task002

状态：历史任务（未完成）

目标：在 M1/M2 基础上完成 M3 可维护性重构，移除 `push()` 兼容包装、迁移 RSS 源硬编码，并收敛过程性文档。

正式入口：
- 契约：[spec/task002/contract.md](/Users/lanser/Code/Claw_news/spec/task002/contract.md)
- 设计：[spec/task002/design.md](/Users/lanser/Code/Claw_news/spec/task002/design.md)
- 计划：[spec/task002/plan.md](/Users/lanser/Code/Claw_news/spec/task002/plan.md)
- 评审：[spec/task002/review.md](/Users/lanser/Code/Claw_news/spec/task002/review.md)
- 归档：[spec/task002/done.md](/Users/lanser/Code/Claw_news/spec/task002/done.md)

历史来源：
- 原契约：[spec/task002/attachments/spec.md](/Users/lanser/Code/Claw_news/spec/task002/attachments/spec.md)

## task003

状态：已完成

目标：在不破坏旧 CLI 的前提下，为仓库新增 FastAPI + APScheduler + OpenAI-compatible LLM + 企业微信机器人的 AI 助手服务 MVP。

正式入口：
- 契约：[spec/task003/contract.md](/Users/lanser/Code/Claw_news/spec/task003/contract.md)
- 设计：[spec/task003/design.md](/Users/lanser/Code/Claw_news/spec/task003/design.md)
- 计划：[spec/task003/plan.md](/Users/lanser/Code/Claw_news/spec/task003/plan.md)
- 评审：[spec/task003/review.md](/Users/lanser/Code/Claw_news/spec/task003/review.md)
- 归档：[spec/task003/done.md](/Users/lanser/Code/Claw_news/spec/task003/done.md)

历史来源：
- 原契约：[spec/task003/attachments/spec.md](/Users/lanser/Code/Claw_news/spec/task003/attachments/spec.md)
- 原评审：[spec/task003/attachments/review_report.md](/Users/lanser/Code/Claw_news/spec/task003/attachments/review_report.md)

## task004

状态：规划中

目标：完善 AI 助手服务交付质量，解决原文链接可用性、内部 scheduler 开关和服务模式验证闭环问题。

正式入口：
- 契约：[spec/task004/contract.md](/Users/lanser/Code/Claw_news/spec/task004/contract.md)
- 设计：[spec/task004/design.md](/Users/lanser/Code/Claw_news/spec/task004/design.md)
- 计划：[spec/task004/plan.md](/Users/lanser/Code/Claw_news/spec/task004/plan.md)
- 评审：[spec/task004/review.md](/Users/lanser/Code/Claw_news/spec/task004/review.md)
- 归档：[spec/task004/done.md](/Users/lanser/Code/Claw_news/spec/task004/done.md)

历史来源：
- 原契约：[spec/task004/attachments/spec.md](/Users/lanser/Code/Claw_news/spec/task004/attachments/spec.md)

## task005

状态：已完成

目标：建立统一的任务文档目录规范，让每个 task 的契约、设计、计划、评审和目标都能快速定位。

正式入口：
- 契约：[spec/task005/contract.md](/Users/lanser/Code/Claw_news/spec/task005/contract.md)
- 设计：[spec/task005/design.md](/Users/lanser/Code/Claw_news/spec/task005/design.md)
- 计划：[spec/task005/plan.md](/Users/lanser/Code/Claw_news/spec/task005/plan.md)
- 评审：[spec/task005/review.md](/Users/lanser/Code/Claw_news/spec/task005/review.md)
- 归档：[spec/task005/done.md](/Users/lanser/Code/Claw_news/spec/task005/done.md)

历史来源：
- 原契约：[spec/task005/attachments/spec.md](/Users/lanser/Code/Claw_news/spec/task005/attachments/spec.md)

## task006

状态：规划中

目标：统一 AI 日报正式发布流程，收敛新旧链路为一套服务化发布系统，并完成主题桶、规则轻分类与关键词降级的评分增强。

正式入口：
- 契约：[spec/task006/contract.md](/Users/lanser/Code/Claw_news/spec/task006/contract.md)
- 设计：[spec/task006/design.md](/Users/lanser/Code/Claw_news/spec/task006/design.md)
- 计划：[spec/task006/plan.md](/Users/lanser/Code/Claw_news/spec/task006/plan.md)
- 评审：[spec/task006/review.md](/Users/lanser/Code/Claw_news/spec/task006/review.md)
- 归档：[spec/task006/done.md](/Users/lanser/Code/Claw_news/spec/task006/done.md)

详细原文：
- 设计：[docs/tasks/task006/design.md](/Users/lanser/Code/Claw_news/docs/tasks/task006/design.md)
- 实施文档：[docs/tasks/task006/plan.md](/Users/lanser/Code/Claw_news/docs/tasks/task006/plan.md)

## task007

状态：规划中

目标：通过 SSH 反向隧道解决国内服务器无法访问 HuggingFace/GitHub 等境外源的问题，利用本地 Clash Verge 代理出口，不改项目代码。

正式入口：
- 契约：[spec/task007/contract.md](/Users/lanser/Code/Claw_news/spec/task007/contract.md)
- 设计：[spec/task007/design.md](/Users/lanser/Code/Claw_news/spec/task007/design.md)
- 计划：[spec/task007/plan.md](/Users/lanser/Code/Claw_news/spec/task007/plan.md)

详细原文：
- 设计：[docs/tasks/task007/design.md](/Users/lanser/Code/Claw_news/docs/tasks/task007/design.md)
- 实施文档：[docs/tasks/task007/plan.md](/Users/lanser/Code/Claw_news/docs/tasks/task007/plan.md)
