# Shared Roles And Templates

本目录用于承载跨 task 复用的角色划定、契约生成模板和 review 模板。

这些文件的语义是：

1. 不属于某个业务 task 的交付结果
2. 用于指导后续 task 的设计、开发和评审方式
3. 应与 `spec/taskNNN/` 的任务文档分开管理

当前共享入口如下：

1. 开发执行者角色：[developer-role.md](/Users/lanser/Code/Claw_news/spec/meta/developer-role.md)
2. 契约生成模板：[spec-author-template.md](/Users/lanser/Code/Claw_news/spec/meta/spec-author-template.md)
3. Review 模板：[review-template.md](/Users/lanser/Code/Claw_news/spec/meta/review-template.md)

历史来源：

1. `spec/task001/attachments/ds_developer.md`
2. `spec/task001/attachments/gpt_plan.md`
3. `spec/task001/attachments/gpt_review.md`

迁移原则：

1. 先建立共享入口
2. 暂不删除 task001 下的历史原件
3. 后续若要彻底收口，再决定是否只保留 `spec/meta/`
