# Task003 Design

## 本轮目标

一句话版本：

在当前仓库内以“同仓双入口”方式新增 AI 助手服务 MVP，同时保留旧 CLI 主链路不被破坏。

详细目标：

1. 新增 `app/` 服务入口，承载 RSS 抓取、LLM 摘要、企业微信推送和定时运行
2. 旧 `main.py` 继续保留，避免把脚本式退出语义硬塞进服务进程
3. LLM 配置改为通用 `OpenAI-compatible` 方式，降低模型成本绑定风险
4. 维持“候选 10 条、展示 5 条、标题带原文链接、复用 RSS 评分逻辑”的设计结论

## 设计结论

1. 采用“融合到当前仓库”的方案，而不是独立新仓
2. 运行形态从“服务器外部定时调脚本”演进为“常驻服务 + 内部 scheduler”
3. 迁移期允许保留“服务器外部定时调用 HTTP”的过渡模式
4. 服务内核必须独立于 CLI，统一由 `news_agent.run_once()` 串联执行

## 关键约束

1. 旧 CLI 不重写
2. 不引入数据库、前端、回调、多 Agent 运行时等超出 MVP 的能力
3. 默认按单实例、单活部署理解 scheduler
4. 设计和评审都必须以 Task003 契约为准

## 详细设计来源

Task003 的完整设计说明见下列历史设计文档：

- [docs/tasks/task003/design.md](/Users/lanser/Code/Claw_news/docs/tasks/task003/design.md)
- [docs/tasks/task003/design-review.md](/Users/lanser/Code/Claw_news/docs/tasks/task003/design-review.md)
- [docs/tasks/task003/one-page.md](/Users/lanser/Code/Claw_news/docs/tasks/task003/one-page.md)
- [docs/tasks/task003/index.md](/Users/lanser/Code/Claw_news/docs/tasks/task003/index.md)
