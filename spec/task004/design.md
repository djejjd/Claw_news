# Task004 Design

## 本轮目标

一句话版本：

不扩业务能力，只把 AI 助手服务补到“可稳定交付”的状态。

详细目标：

1. 让企业微信里的原文链接真正可用
2. 让内部 scheduler 能通过显式配置开关控制
3. 让服务模式的测试、CI、部署说明形成闭环

## 设计结论

1. 默认继续使用企业微信 `text` 消息，但每条新闻必须显式给出原文 URL
2. 新增 `ENABLE_INTERNAL_SCHEDULER`，明确区分内部调度和外部 HTTP 调度
3. 不改 Task003 的主架构，只做交付层增强

## 关键约束

1. 不扩数据库、多 key 调度、provider 专用适配等范围外能力
2. 不重写旧 CLI
3. 所有变更都必须能被测试和文档覆盖

## 详细设计来源

- [docs/tasks/task004/design.md](/Users/lanser/Code/Claw_news/docs/tasks/task004/design.md)
