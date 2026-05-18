# Task007 Contract

## 任务目标

解决部署在国内腾讯云服务器上的 AI 日报服务无法访问境外数据源（HuggingFace、GitHub）的问题，通过 SSH 反向隧道将服务器流量经本地 Clash 代理出口，无需修改项目代码。

1. 服务器可以正常访问 HuggingFace API、GitHub API 等境外源
2. 隧道方案不引入额外的付费服务或外部依赖
3. 操作步骤可复现、可验证
4. 不影响现有采集器和推送链路的稳定性

## 当前状态

1. 本任务是新建任务
2. 本文件是 Task007 的唯一正式契约
3. 开发和 review 必须以本文件作为唯一验收基线

## 文档入口

- 设计：[design.md](/Users/lanser/Code/Claw_news/spec/task007/design.md)
- 计划：[plan.md](/Users/lanser/Code/Claw_news/spec/task007/plan.md)
- 详细设计原文：[docs/tasks/task007/design.md](/Users/lanser/Code/Claw_news/docs/tasks/task007/design.md)
- 开发实施原文：[docs/tasks/task007/plan.md](/Users/lanser/Code/Claw_news/docs/tasks/task007/plan.md)

## 前置条件

1. 本地 Mac 已安装并运行 Clash Verge，代理端口 `127.0.0.1:7897`
2. 本地 Mac 可通过 SSH 连接到腾讯云服务器
3. 服务器上已有项目代码并运行 Docker
4. 项目代码中 `HF_PROXY` 环境变量支持已实现（`collectors/huggingface.py` 接受 proxy 参数）

## In Scope

1. SSH 反向隧道建立：服务器 `127.0.0.1:8899` → 本地 Mac `127.0.0.1:7897` → Clash Verge → 境外
2. 服务器 `.env` 配置 `HF_PROXY=http://127.0.0.1:8899`
3. 验证 HuggingFace 采集成功
4. 隧道保活方案（autossh）

## Out of Scope

1. 不修改项目代码（已有 `HF_PROXY` 支持已经足够）
2. 不安装额外的服务器端代理客户端
3. 不购买第三方代理服务
4. 不修改 Dockerfile、docker-compose.yml

## Review Checklist

- [ ] 服务器可通过代理访问 `https://huggingface.co`
- [ ] `HF_PROXY=http://127.0.0.1:8899` 已在服务器 `.env` 中配置
- [ ] HuggingFace 采集不再出现 `curl_cffi.requests.exceptions.Timeout` 错误
- [ ] ingest 日志中出现 HuggingFace 成功采集的记录
- [ ] autossh 或心跳机制保证隧道不会意外断开
- [ ] 隧道断开时不影响 RSS 源等其他采集器正常运行
