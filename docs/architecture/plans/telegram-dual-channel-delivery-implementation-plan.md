# Telegram 双通道推送实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` 或 `superpowers:executing-plans` 按任务逐项执行。步骤使用 checkbox 跟踪。

**目标：** 在不改变未配置场景的企业微信行为前提下，增加 Telegram 推送、独立通道投递状态和失败通道补发能力。

**架构：** `AppConfig` 只负责可选 Telegram 凭据的成对校验；`app/delivery` 负责无密钥的通道状态、稳定 `delivery_id` 和原子待完成投递记录；`pusher/telegram.py` 负责 Telegram HTML 文本和 Bot API 协议；发布链路优先恢复待完成记录，按 delivery 状态跳过已成功通道，仅投递未成功通道。选材和去重持久化只在所有已启用通道完成后执行。

**技术栈：** Python 3.11+、httpx、pytest、Ruff、Telegram Bot API `sendMessage`。

## 全局约束

- 以 `docs/architecture/decisions/telegram-dual-channel-delivery-design.md` 为唯一设计契约。
- 中文文档优先；不得在任何文件、测试、日志或交付中提交真实 Token/Chat ID。
- 所有 HTTP 测试使用 mock transport 或注入 client，禁止真实 Telegram 请求。
- 先写失败测试，再写最小实现；任务完成前不进入下一任务。
- 本期不改选材、评分、GitHub 排名和企业微信 renderer 的输出格式。
- 每个任务 commit 前必须由主审核 AI 检查完整 diff；不得自行 push、merge、deploy 或真实发消息。

---

## Task 1：Telegram 配置与通道投递状态契约

**依赖：** 已批准的双通道设计；无代码任务依赖。
**允许并行：** 无。
**完成状态：** 未开始。

### 1. 背景

现有 `AppConfig` 只含必填的企业微信 webhook；`publish_status.json` 只有整体 `status/pushed/errors`，无法判定某个通道是否已成功投递。

### 2. 目标

为 Telegram 增加成对可选配置；建立不含密钥的 `DeliveryState`、`ChannelResult`、稳定 `delivery_id` 和 JSON 序列化契约，供后续 pipeline 读取和写入。

### 3. 前置依赖

`docs/architecture/decisions/telegram-dual-channel-delivery-design.md` 第 4、6、7 节。

### 4. 输入与输出契约

- 输入：`TELEGRAM_BOT_TOKEN` 与 `TELEGRAM_CHAT_ID` 环境变量。
- 输出：`AppConfig.telegram_bot_token: str | None`、`AppConfig.telegram_chat_id: str | None`；两项必须同时为 `None` 或非空。
- 输出：`app.delivery.state.make_delivery_id(date: str, period: str, content: str) -> str`，返回 `"{date}-{period}-{sha256[:16]}"`。
- 输出：`DeliveryState.can_attempt(channel: str) -> bool`，仅当通道未记录成功时为真；`to_dict()` 不包含任何配置或消息正文。

### 5. 修改范围

- 新建：`app/delivery/__init__.py`、`app/delivery/state.py`、`tests/test_delivery_state.py`。
- 修改：`app/config.py`、`tests/test_app_config.py`、`.env.example`、`README.md`、`docs/operations/deploy/server-guide.md`。

### 6. 禁止事项

- 不创建 `.env`，不读取或输出服务器真实配置。
- 不将 Token 或 Chat ID 写进 `publish_status.json`、repr、断言文本或文档示例。
- 不修改 `run_pipeline`、企业微信发送或摘要渲染。

### 7. 执行要求

1. `AppConfig.__repr__` 对 Telegram token 与 Chat ID 都只显示固定脱敏标志；
2. 单字段配置必须抛出 `ValueError`，错误仅报告变量名；
3. 状态模型只接受 `pending`、`succeeded`、`failed`，未知状态抛出 `ValueError`；
4. 同一 date、period、content 必须产生相同 `delivery_id`，内容变化必须产生不同值。

### 8. 实施步骤

- [ ] 1. 在 `tests/test_app_config.py` 写入三组失败/成功测试：两个 Telegram 变量均空、均有值、仅一个有值；并断言 repr 不含 token/chat id。
- [ ] 2. 运行 `./venv/bin/pytest tests/test_app_config.py -v`，预期新用例因字段/校验不存在失败。
- [ ] 3. 在 `tests/test_delivery_state.py` 写入：稳定 id、内容变化、成功通道跳过、失败通道可重试、序列化不含 secret 字段。
- [ ] 4. 运行 `./venv/bin/pytest tests/test_delivery_state.py -v`，预期因模块不存在失败。
- [ ] 5. 新建 `app/delivery/state.py`，定义：

```python
@dataclass(frozen=True)
class ChannelResult:
    enabled: bool
    status: Literal["pending", "succeeded", "failed"]
    attempted_at: str | None = None
    error: str | None = None

@dataclass
class DeliveryState:
    delivery_id: str
    channels: dict[str, ChannelResult]

    def can_attempt(self, channel: str) -> bool: ...
    def to_dict(self) -> dict[str, object]: ...

def make_delivery_id(date: str, period: str, content: str) -> str: ...
```

- [ ] 6. 最小修改 `app/config.py`：读取两个变量、成对校验、将可选字段加入 dataclass 和脱敏 repr。
- [ ] 7. 在 `.env.example`、README 环境变量表和服务器部署文档加入仅含占位符的 Telegram 两字段及“成对配置”说明。
- [ ] 8. 运行 `./venv/bin/pytest tests/test_app_config.py tests/test_delivery_state.py -v`，预期全部通过。
- [ ] 9. 运行 `make lint`、`ruff format --check .`、`git diff --check`；向主审核 AI 提交完整 diff 和结果，获准后 commit：`feat: add telegram delivery configuration contract`。

### 9. 验收标准

- 成对配置正确加载，半配置启动失败；
- 生成的 delivery state 可确定是否跳过成功通道；
- 状态序列化、repr、示例文档中均无密钥或真实 Chat ID；
- 精确测试、lint、格式和 diff 检查通过。

### 10. 检查命令

```bash
./venv/bin/pytest tests/test_app_config.py tests/test_delivery_state.py -v
make lint
ruff format --check .
git diff --check
```

### 11. 交付前自检

- [ ] 仅改动本 Task 范围内文件；
- [ ] 所有新测试先失败后通过；
- [ ] 搜索 `TELEGRAM_BOT_TOKEN|TELEGRAM_CHAT_ID` 的结果不含真实值；
- [ ] `git diff --check` 无输出；
- [ ] 不存在 `.env`、data 文件或调试输出进入暂存区。

### 12. 交付格式

按 AGENTS.md 固定十段交付格式，另附：配置兼容矩阵、`delivery_id` 测试输入与结果、密钥扫描结果。

---

## Task 2：Telegram 渲染器与 Bot API 发送器

**依赖：** Task 1。
**允许并行：** 无。
**完成状态：** 未开始。

### 1. 背景

企业微信 markdown 与 Telegram HTML 的转义规则不同，不能复用同一 renderer。Telegram API 成功还要求响应 JSON 的 `ok=true`。

### 2. 目标

创建独立 Telegram HTML 渲染和异步发送器，安全处理链接/文本，按 4096 字符分段，并将 API 故障转换为无敏感信息的异常。

### 3. 前置依赖

Task 1 的配置契约；设计第 5、7 节。

### 4. 输入与输出契约

- 输入：`SummaryResult`、GitHub 列表、已推送 URL。
- 输出：`render_telegram_digest(...) -> list[str]`，每项为非空 HTML 文本且长度不大于 4096。
- 输出：`TelegramPusher.push_messages(messages: list[str]) -> TelegramPushResult`。
- 请求：`POST https://api.telegram.org/bot{token}/sendMessage`，JSON 含 `chat_id`、`text`、`parse_mode: "HTML"`、`link_preview_options: {"is_disabled": true}`。
- 成功：HTTP 2xx 且 JSON `ok is True`；否则抛出 `TelegramError`，错误文本不得含 token/chat id/消息正文。

### 5. 修改范围

- 新建：`app/renderers/telegram_html.py`、`pusher/telegram.py`、`tests/test_telegram_html_renderer.py`、`tests/test_telegram_pusher.py`。
- 可修改：`pusher/__init__.py`（仅导出必要类型）。

### 6. 禁止事项

- 不修改 `pusher/wecom.py`、`app/pipeline/news_pipeline.py` 或状态持久化。
- 不调用真实 API，不增加 Telegram SDK 依赖。
- 不允许未转义的 LLM 文本直接进入 HTML。

### 7. 执行要求

1. 用 `html.escape(..., quote=True)` 处理所有非 URL 的动态文本；
2. URL 必须以 `http://` 或 `https://` 开头才可进入 `<a href>`，否则只输出纯文本标题；
3. 按行聚合切分，保证每段 ≤4096；空行不生成独立段；
4. 注入 `httpx.AsyncClient` 时不得关闭它；内部创建 client 时必须关闭；
5. 429 解析 `parameters.retry_after` 形成如 `telegram_api: 429 retry_after=30` 的脱敏错误。

### 8. 实施步骤

- [ ] 1. 在 `tests/test_telegram_html_renderer.py` 写入 HTML 字符转义、恶意 URL 降级、正常链接、4096 边界和超长单行测试。
- [ ] 2. 运行 `./venv/bin/pytest tests/test_telegram_html_renderer.py -v`，预期 import 失败。
- [ ] 3. 在 `tests/test_telegram_pusher.py` 用 `httpx.MockTransport` 写入：正确 endpoint/payload、HTTP 500、`ok=false`、429 retry_after、多段顺序发送和第二段失败停止。
- [ ] 4. 运行 `./venv/bin/pytest tests/test_telegram_pusher.py -v`，预期 import 失败。
- [ ] 5. 最小实现 `telegram_html.py`：渲染标题、新闻条目、来源、每日判断与 GitHub 区块；添加 `split_telegram_text(text, limit=4096)`。
- [ ] 6. 最小实现 `pusher/telegram.py`：`TelegramError`、`TelegramPushResult`、`TelegramPusher`，以 injected client 执行 sendMessage。
- [ ] 7. 运行两个精确测试文件，预期全部通过。
- [ ] 8. 运行 `make lint`、`ruff format --check .`、`git diff --check`；主审核 AI 通过完整 diff 后 commit：`feat: add telegram html pusher`。

### 9. 验收标准

- 所有动态 HTML 被转义，非法链接不能作为 href；
- 所有 Telegram 段满足限制且顺序稳定；
- 只有 HTTP 和 API 语义同时成功时才返回成功；
- 测试中验证没有真实网络访问，也没有泄露配置。

### 10. 检查命令

```bash
./venv/bin/pytest tests/test_telegram_html_renderer.py tests/test_telegram_pusher.py -v
make lint
ruff format --check .
git diff --check
```

### 11. 交付前自检

- [ ] 发送 URL 固定为官方 API base URL；
- [ ] 模拟响应覆盖 HTTP 与 API 级错误；
- [ ] renderer 不依赖企业微信 markdown 输出；
- [ ] 不引入第三方 Telegram SDK；
- [ ] 任务外文件未修改。

### 12. 交付格式

按 AGENTS.md 固定十段交付格式，另附：分段边界测试结果、API payload 脱敏样例、异常分类矩阵。

---

## Task 3：发布链路双通道接入、补发与验收

**依赖：** Task 1、Task 2。
**允许并行：** 无。
**完成状态：** 未开始。

### 1. 背景

`run_pipeline` 当前企微成功后立即写入去重键、摘要和整体发布状态。双通道下必须先保存通道结果，再决定是否完成业务持久化。

### 2. 目标

接入两个通道：按 `delivery_id` 跳过成功通道、只补发失败通道、在所有启用通道成功后才落业务状态，并让 `/health` 与 API 结果正确显示 `ok/degraded/failed`。

### 3. 前置依赖

Task 1 的状态模型与 Task 2 的 renderer/pusher；设计第 6 至 8 节。

### 4. 输入与输出契约

- 输入：已生成的企业微信 markdown、Telegram HTML 段、`AppConfig`、先前 `publish_status.json` 和可选的 `data/pending_deliveries/{date}-{period}.json`。
- 输出：`publish_status.json` 增加 `delivery` 字段；`channels.wecom`/`channels.telegram` 各含 enabled、status、attempted_at、error。
- 输出：`PublishResult.status` 为 `ok`（所有启用通道成功）、`degraded`（至少一个成功且至少一个失败）、`failed`（没有启用通道成功）或既有 `skipped`。
- 兼容：Telegram 未配置时，现有企微成功路径仍为 `ok`、`pushed=true`。

### 5. 修改范围

- 修改：`app/pipeline/news_pipeline.py`、`app/tools/summary_result.py`、`app/main.py`（仅在需要展示状态时）、`tests/test_news_pipeline.py`、`tests/test_app_api.py`、`tests/test_main.py`。
- 新建：`app/delivery/store.py`、`tests/test_delivery_store.py`，负责原子读取、写入和删除 `data/pending_deliveries/{date}-{period}.json`；记录只含渲染文本、通道状态和最终业务持久化所需的公开数据。
- 修改：`docs/operations/verify-after-deploy.md`、`README.md`。

### 6. 禁止事项

- 不修改候选池、评分、相关性、GitHub 排名、RSS 拉取和企业微信消息格式。
- 不把 Telegram 配置、密钥或消息正文写入 `publish_status.json`；消息正文只能写入本地待完成投递记录。
- 不在自动化测试、`make dry-run` 或部署时发送真实 Telegram。
- 不把“某通道成功”误写为“所有启用通道完成”。

### 7. 执行要求

1. `delivery_id` 使用首次企业微信 markdown 的稳定内容生成；Telegram 重渲染不影响已完成判定；
2. 同日同期有待完成记录时，必须直接恢复其消息和业务数据，不得重新调用 LLM、选材或企微；
3. 待完成记录必须在任何通道发送前原子写入；写入失败时不发送；
4. 每个通道尝试完成后立刻原子更新待完成记录，进程中断后也能识别已成功通道；
5. 仅在全部启用通道成功后执行 GitHub 曝光、`merge_pushed_urls`、`merge_published_keys` 和 `write_digest`，然后删除待完成记录；
6. Telegram 未配置时不导入/构造 TelegramPusher，不增加 API 调用；
7. `errors` 使用 `wecom:`、`telegram:` 前缀，内容脱敏。

### 8. 实施步骤

- [ ] 1. 在 `tests/test_news_pipeline.py` 写入未配置 Telegram 的回归测试，确认企微单通道仍成功并且不构造 TelegramPusher。
- [ ] 2. 写入企微成功/Telegram 失败：整体 `degraded`、企微状态 `succeeded`、Telegram `failed`、未写去重/曝光/digest 的测试。
- [ ] 3. 写入企微已成功、Telegram 失败后的第二次执行：从待完成记录恢复原样 Telegram 文本，只调用 Telegram、不调用 LLM 或企微；Telegram 成功后变 `ok` 并完成业务持久化的测试。
- [ ] 4. 写入两通道成功和两通道均失败的测试；检查状态 JSON 不含配置值。
- [ ] 5. 运行相关精确测试，预期因双通道行为尚不存在失败。
- [ ] 6. 在 `app/delivery/store.py` 写入待完成记录的原子 load/save/delete；损坏文件必须产生专用异常并保留原文件。
- [ ] 7. 在 `news_pipeline.py` 抽取小型通道投递 helper：优先恢复待完成记录；否则在 LLM/渲染完成后先保存新记录；逐通道尝试后立即更新记录并归并整体结果；保留已有单通道返回字段兼容。
- [ ] 8. 将原企微 try/except 替换为 helper 调用；当配置完整时渲染并投递 Telegram；成功通道按 delivery state 跳过。
- [ ] 9. 将业务状态持久化移动至“所有启用通道成功”分支；成功后删除待完成记录；失败或 degraded 分支仍写通道状态和 `PublishResult`。
- [ ] 10. 更新 `/health` 读取逻辑和运维文档，说明 `channels`、`degraded` 与补发语义；更新 README 的 Telegram 配置/验证说明。
- [ ] 11. 运行 `./venv/bin/pytest tests/test_news_pipeline.py tests/test_app_api.py tests/test_main.py tests/test_delivery_state.py tests/test_telegram_html_renderer.py tests/test_telegram_pusher.py tests/test_delivery_store.py -v`，预期通过。
- [ ] 12. 运行 `make test`、`make lint`、`ruff format --check .`、`git diff --check`；检查 `git diff --name-only` 无范围外文件。
- [ ] 13. 主审核 AI 完成规格与质量两轮审核后，才 commit：`feat: deliver news digest to telegram`。

### 9. 验收标准

- 未配置 Telegram 时企业微信路径与原行为一致；
- 任一失败通道只在后续同 delivery_id 下补发自身；
- 全部通道成功前不写去重、曝光和摘要业务状态；
- `publish_status.json` 可供 `/health` 读取、可审计且无秘密；
- 全量测试、lint、格式与 diff 检查通过。

### 10. 检查命令

```bash
./venv/bin/pytest tests/test_news_pipeline.py tests/test_app_api.py tests/test_main.py tests/test_delivery_state.py tests/test_telegram_html_renderer.py tests/test_telegram_pusher.py -v
make test
make lint
ruff format --check .
git diff --check
```

### 11. 交付前自检

- [ ] 三种整体状态与四种通道组合有测试证据；
- [ ] 读取旧状态文件不会异常；
- [ ] 每次通道完成后均先原子落状态；
- [ ] 只有完整成功才写业务去重状态；
- [ ] 没有真实 Telegram 网络调用或敏感信息；
- [ ] 完整 diff 已由两名独立 reviewer 审核。

### 12. 交付格式

按 AGENTS.md 固定十段交付格式，另附：通道组合验收表、持久化顺序证据、未验证项（仅真实 Telegram 发消息，需用户在发版后明确授权）。
