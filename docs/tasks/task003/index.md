# 本次新增文档阅读顺序

以下文档均为本次新增，开发开始前必须先阅读并确认。

## 1. 必读顺序

1. 契约 spec
   - [spec/task003/contract.md](/Users/lanser/Code/Claw_news/spec/task003/contract.md)
2. 设计文档
   - [docs/tasks/task003/design.md](/Users/lanser/Code/Claw_news/docs/tasks/task003/design.md)
3. 设计审查结论
   - [docs/tasks/task003/design-review.md](/Users/lanser/Code/Claw_news/docs/tasks/task003/design-review.md)
4. 一页开发与评审清单
   - [docs/tasks/task003/one-page.md](/Users/lanser/Code/Claw_news/docs/tasks/task003/one-page.md)
5. 实施计划
   - [docs/tasks/task003/plan.md](/Users/lanser/Code/Claw_news/docs/tasks/task003/plan.md)

## 2. 每份文档的作用

1. `spec/task003/contract.md`
   - 定义不可变更的验收契约
2. `...service-design.md`
   - 解释为什么这么设计，边界是什么
3. `...design-review.md`
   - 给出阻塞项、重要风险和通过条件
4. `...one-page.md`
   - 给开发和 reviewer 的一页版摘要
5. `...implementation-plan.md`
   - 给执行开发的逐任务落地计划

## 3. 开发前确认项

开发开始前，开发者必须口头或书面确认以下四点：

1. 本轮主部署模式是“服务内 scheduler”
2. 候选新闻 `10` 条，最终展示 `5` 条
3. 每条标题需要带原文跳转链接
4. 复用原项目 RSS 评分逻辑
