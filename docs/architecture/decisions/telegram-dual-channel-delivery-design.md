# Telegram 双通道推送设计

## 1. 背景

当前日报只通过企业微信机器人发送。正式环境已经在 `.env` 保存 Telegram Bot 的凭据，但现有发布链路既不会读取这些字段，也不能表达“一个通道成功、另一个通道失败”的持久状态。若直接在企业微信后追加一次 Telegram 请求，重试时会重复发送已经成功的企业微信消息。

## 2. 目标

1. 在保留企业微信现有行为的前提下，向已配置的 Telegram 私聊同时发送同一份日报；
2. 每个通道分别记录成功或失败，Telegram 单独失败时后续仅补发 Telegram；
3. 未配置 Telegram 时，发布语义、企业微信消息和已有状态兼容；
4. 不将 Bot Token、Chat ID、原始 Telegram 响应写入日志、状态文件、测试 fixture 或仓库。

## 3. 范围与非目标

本期包含 `sendMessage` 文本推送、HTML 格式渲染、Telegram 单通道补发和可审计状态。

本期不包含群组推送、多 Chat ID、图片/文件、交互按钮、定时重试后台任务、修改选材/评分逻辑或替换企业微信。

## 4. 配置契约

新增两个可选环境变量：

```dotenv
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

- 两项都为空：Telegram 禁用，企业微信为唯一已启用通道；
- 两项都非空：Telegram 启用；
- 仅设置其中一项：应用启动失败并指出缺少的配对字段；
- `AppConfig.__repr__` 只显示脱敏后的 token，绝不显示原文；
- `.env.example`、README 和部署文档仅写变量名和占位符。

## 5. 消息契约

同一份 `SummaryResult` 分别由现有企业微信 renderer 与新增 Telegram renderer 生成。

- Telegram 使用 Bot API `sendMessage` 的 `parse_mode=HTML`；
- 标题、摘要、来源和 LLM 输出均进行 HTML 转义；链接只允许 HTTP/HTTPS URL；
- 单段文本上限为 4096 个字符，按完整行切分；单个超长行安全截断；
- 多段按顺序发送，某段失败即停止，已成功段记录为该通道未完成并在下次重新投递整份 Telegram 摘要；
- 关闭网页预览，避免一份日报产生大量预览卡片。

## 6. 双通道投递与状态契约

发布链路首次渲染摘要后，创建稳定的 `delivery_id`（由日期、期次和摘要内容哈希构成），并在 `data/pending_deliveries/{date}-{period}.json` 原子保存待完成投递记录。该记录包含已渲染的企业微信与 Telegram 文本、通道状态、所选内容的公开持久化数据和 `delivery_id`；不包含任何配置、密钥或 Telegram 原始响应。

后续同一日期、期次的执行优先读取该待完成记录：不会再次调用 LLM 或企业微信，只重试未成功的通道，并使用第一次渲染的原样文本。所有已启用通道成功并完成业务持久化后，原子删除待完成记录。

```json
{
  "delivery_id": "2026-07-13-morning-...",
  "channels": {
    "wecom": {"enabled": true, "status": "succeeded", "attempted_at": "...", "error": null},
    "telegram": {"enabled": true, "status": "failed", "attempted_at": "...", "error": "telegram_http: 429"}
  }
}
```

- 启用且状态为 `succeeded` 的通道在相同 `delivery_id` 下跳过；
- 启用且未成功的通道会尝试投递；
- 待完成记录写入失败时不发送任何通道，避免无法可靠补发的部分投递；
- 任何已启用通道失败，整体 `publish_status.status` 为 `degraded`、`pushed` 为 `true`（至少一个通道成功）或 `false`（没有通道成功）；
- 所有已启用通道成功，整体为 `ok`；
- 通道错误保存为有限、脱敏的错误类别和 HTTP/API 码，不保存 token、Chat ID、消息正文或 Telegram 返回体；
- 选中新闻、去重键、GitHub 曝光及摘要存档只在所有已启用通道成功后写入，避免部分投递造成后续选材丢失；
- `delivery_id` 改变（摘要内容或日期/期次改变）视为新投递，不复用旧状态。

## 7. 错误处理

- 网络、超时、非 2xx、无效 JSON、Telegram `ok=false` 都是 Telegram 通道失败；
- 成功响应必须同时满足 HTTP 成功与 JSON `ok=true`；
- Telegram `429` 记录 `retry_after`（若响应提供），本期不在本次 HTTP 请求中 sleep 重试；
- 配置错误在启动期暴露，不允许静默禁用已部分配置的 Telegram；
- 企业微信异常继续沿用现有失败分类，但纳入统一通道结果。
- 待完成记录损坏时本次发布返回 `failed` 并保留文件供人工排查，不覆盖或重新生成摘要。

## 8. 测试与验收

必须覆盖：未配置兼容、配置半缺失、Telegram 请求路径/payload、HTML 转义、4096 字符切分、HTTP/API 失败、企微成功+Telegram 失败、仅重试 Telegram、两通道成功及状态文件不含密钥。所有 HTTP 测试注入 `httpx.AsyncClient` 或 mock transport，禁止真实调用 Telegram。

验收时运行精确测试、完整 `make test`、`make lint`、`ruff format --check .` 与 `git diff --check`。真实 Telegram 测试消息只在代码审核、发版和用户明确授权后进行。
