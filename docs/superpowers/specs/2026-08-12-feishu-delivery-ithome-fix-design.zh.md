# 飞书推送通道 + IT之家来源权重修复 设计文档

## 1. 目标

1. **修复 IT之家来源权重失效**：让 `feeds.yaml` 中 ithome 的策略字段（低权重、严格过滤、短保留期）真正生效，从源头缓解"推送几乎全是 IT之家"的问题。
2. **新增飞书推送通道**：复用 hermes 已建联的飞书应用机器人凭证，以交互卡片形式把每日热点日报推送到飞书群。
3. **停用企微与 Telegram**：企微通道停用不删，Telegram 通道停用，只保留飞书作为交付通道。

本轮不动评分模型、不重构选材逻辑、不引入新依赖（httpx 直连飞书 REST API）。

## 2. 当前状态与问题根因

### 2.1 IT之家权重失效

`app/content/source_policy.py` 的 `_BUILTIN_SOURCE_POLICIES` 明确给 ithome 降权：

```python
"ithome": SourcePolicy("ithome", "fast_news", 24, 2.0, "strict"),
```

即 `quality_weight=2.0`（低于默认 3.0）、`filter_profile="strict"`（比 standard 更严）、`retention_hours=24`（保留更短）。

但 `feeds.yaml` 中 ithome 条目没有携带这些字段：

```yaml
- url: https://www.ithome.com/rss/
  source: ithome
```

`build_source_policy_registry()` 用默认值 `3.0 / standard / 48h` 重建 registry，**覆盖了 builtin 的降权配置**。效果是：IT之家权重与别家相同、过滤更松、保留更久。

远程实际数据（08-11）：候选池 278 条中 ithome 占 242 条（87%），推送 6 条全部来自 ithome。

### 2.2 交付通道现状

- 企微：`WeComPusher`（`pusher/wecom.py`）+ `app/renderers/wecom_markdown.py`，webhook 发 markdown
- Telegram：`TelegramPusher`（`pusher/telegram.py`）+ `app/renderers/telegram_html.py`
- 交付决策：`app/pipeline/news_pipeline.py` 的 `_deliver_with_pending()`，企微和 Telegram 都尝试；`_has_telegram_delivery()` 判断 Telegram 是否启用
- 失败持久化：`pending_deliveries/` 目录 + `app/delivery/state.py` 记录各通道 pending/succeeded/failed
- 配置：全部从 `.env` 环境变量加载（`app/config.py`）

### 2.3 飞书凭证来源

hermes（`nousresearch/hermes-agent`，远程 `/home/ubuntu/hermes-data/.env`）已配置飞书应用机器人：

```dotenv
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_CONNECTION_MODE=websocket
FEISHU_DOMAIN=feishu
FEISHU_GROUP_POLICY=open
FEISHU_VERIFICATION_TOKEN=xxx
FEISHU_HOME_CHANNEL=xxx
FEISHU_HOME_CHANNEL_THREAD_ID=xxx
```

Claw_news 复用同一套 `FEISHU_APP_ID` / `FEISHU_APP_SECRET`，以同一机器人身份主动发消息；推送目标先用 `FEISHU_HOME_CHANNEL` 的值作为 `FEISHU_CHAT_ID` 跑通。

## 3. 设计结论

### 3.1 IT之家权重修复（纯配置）

`feeds.yaml` 中 ithome 条目补上显式策略字段：

```yaml
- url: https://www.ithome.com/rss/
  source: ithome
  tier: fast_news
  quality_weight: 2.0
  filter_profile: strict
  retention_hours: 24
```

`_load_yaml_feeds()`（`collectors/ai_rss.py:131`）已保留这些字段，registry 构建时即生效。无需改 Python 代码。

**效果预期（经代码验证）**：
- `compute_final_score = quality_weight + freshness_score`（`selection.py:70`）。修复后 fresh ithome = 2.0 + 3.0 = 5.0，与 24-48h 的 vertical 源（3.5 + 1.5 = 5.0）打平，输给任何更新鲜的源。
- `retention_hours: 24` 会把 24-48h 的 ithome 从候选池整体移除（`ingestion_store.py:465-475`），效果显著。
- 单源多样性惩罚（`selection.py:24,73-79`）第 4 条起 -3.5、第 5 条起 -5.0。修复前 ithome=6.0 使惩罚被淹没；修复后第 3 条 selection_score=3.0，会被 48-72h 的 vertical（4.0）击败——既有惩罚真正生效。
- **注意**：`filter_profile: strict` 不是主杠杆，仅影响"无正向词命中、落到 classifier 复核"的分支（`relevance_filter.py:148,210-231`）。对 tool 类命中正向词的 ithome 文章几乎无约束。不要把 strict 当成主要效果来源。
- **边界**：代码没有"单源硬上限"。若其他源彻底无候选（feed 挂掉），ithome 仍可能填满名额。本轮不引入硬上限（保持最小改动）。

### 3.2 飞书推送架构

#### 3.2.1 配置（`.env`）

```dotenv
# 飞书可选通道；两个字段必须同时填写或同时留空
FEISHU_APP_ID=
FEISHU_APP_SECRET=
# 推送目标 chat_id（群）或 open_id（用户）
FEISHU_CHAT_ID=
```

`app/config.py` 增加：

```python
feishu_app_id: str | None = None
feishu_app_secret: str | None = None
feishu_chat_id: str | None = None
```

校验规则（与 Telegram 相同）：`feishu_app_id` 与 `feishu_app_secret` 必须成对；`feishu_chat_id` 缺省时报错。

#### 3.2.2 发送器 `pusher/feishu.py`

`FeishuPusher`，httpx 直连，不引 lark-oapi：

1. 获取 `tenant_access_token`：
   `POST https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal`
   body `{"app_id", "app_secret"}` → `{"code": 0, "tenant_access_token": "...", "expire": 7200}`
   缓存 token，过期（`expire - 300` 秒）后重取。
2. 发送卡片消息：
   `POST https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id`
   body `{"receive_id": chat_id, "msg_type": "interactive", "content": json_str}`
   成功判定：HTTP 200 且 `body.code == 0`。
   `code == 99991663`（access token 无效）时重取 token 后重试一次。

接口契约（与 `TelegramPusher` 对齐）：

```python
@dataclass(frozen=True)
class FeishuPushResult:
    messages_sent: int

class FeishuPusher:
    def __init__(self, app_id, app_secret, chat_id, client=None): ...
    async def push_card(self, card: dict) -> FeishuPushResult: ...
```

- `client` 可注入，供测试 mock
- 网络错误统一抛 `FeishuError`，消息体不含密钥

#### 3.2.3 渲染器 `app/renderers/feishu_card.py`

`render_feishu_card(result, github_items, pushed_urls, github_recommendations) -> dict`，把企微 markdown 日报映射为飞书交互卡片 JSON（`lark_md` 元素）：

```jsonc
{
  "config": { "wide_screen_mode": true },
  "header": { "title": { "tag": "plain_text", "content": "AI / 游戏 / 工具 热点" }, "template": "blue" },
  "elements": [
    { "tag": "div", "text": { "tag": "lark_md", "content": "【AI】2\n**1.** [标题](url)\n> 摘要 | 重要性：高 | 趋势：上升 — 量子位 · 国内" } },
    { "tag": "hr" },
    { "tag": "note", "elements": [{ "tag": "plain_text", "content": "今日一句话判断：..." }] }
  ]
}
```

复用 `wecom_markdown.py` 的 `_escape_title`、`_source_display`、`MAX_DIGEST_ITEMS` 等已有逻辑，避免重复。

#### 3.2.4 交付决策接入 `app/pipeline/news_pipeline.py`

**⚠️ 这是审查发现的最大缺口**：`_deliver_with_pending()` 的唯一调用点 `news_pipeline.py:881` 被 `_has_telegram_delivery(config)` 独占。Telegram 停用后飞书分支永远执行不到。必须同时改以下三处：

1. **触发条件**（`news_pipeline.py:881`）：`if _has_telegram_delivery(config):` 改为
   `if _has_feishu_delivery(config) or _has_telegram_delivery(config):`
   新增 `_has_feishu_delivery(config)`（`feishu_app_id`/`feishu_app_secret`/`feishu_chat_id` 三者齐全）。
2. **pending 恢复门禁**（`news_pipeline.py:387`）：`if not _has_telegram_delivery(config):` 同样改为同时认飞书，否则 Telegram 停用后 pending 恢复路径一律返回 `telegram_config_missing`。
3. **企微分支改飞书**：`_deliver_with_pending()` 中企微分支（`news_pipeline.py:534`）改为：wecom 配置存在时走 `_attempt_wecom`，否则走 `_attempt_feishu`。`pushed = wecom_ok or feishu_ok or telegram_ok`。

**新增 `_attempt_feishu` 包装**（与 `_attempt_wecom` 同构，`news_pipeline.py:277-284` 风格）：
```python
async def _attempt_feishu(card, app_id, app_secret, chat_id) -> tuple[bool, str | None]:
    try:
        await FeishuPusher(app_id, app_secret, chat_id).push_card(card)
        return True, None
    except FeishuError as exc:
        return False, f"feishu_push: {exc}"
    except Exception as exc:
        return False, f"feishu_push: {type(exc).__name__}"
```
必须 catch，否则 `FeishuError` 冒泡到 `NewsAgent._run`（`news_agent.py:91`）导致 pending 通道状态与文件不更新。

**`_build_pending_payload` 只写入启用的通道**（`news_pipeline.py:230-233` 目前无条件写 wecom+telegram 且 status="pending"）：只写入启用且会被尝试的通道；未启用通道标记为 `skipped`，否则 Telegram 停用后 `_pending_completion_status` 永远判为 "degraded"、pending 文件永不删除（只在 `news_pipeline.py:602-603` 全成功时删）。

#### 3.2.5 失败持久化

复用现有 `pending_deliveries/` + `app/delivery/state.py`。飞书通道失败时状态记为 `failed`，由现有重试机制重发。`DeliveryState.can_attempt`（`state.py:30-32`）与通道名无关，加 `"feishu"` 通道键天然可用。

### 3.3 企微 / Telegram 停用（不删代码）

**⚠️ "webhook 留空即不推（现有逻辑已支持）"是错误表述**，必须改 `app/config.py` 才能实现：

- **`WECOM_WEBHOOK_URL` 必须从 required 改为可选**（`app/config.py:44`）。当前它在 required dict 里，留空会让 `load_config()` 抛 `ValueError`；远程入口 `app/main.py:24` 在**模块导入期**调用 `load_config()`，webhook 留空会导致整个服务（含 APScheduler、ingest 任务）启动失败。
- `main.py:84-86` 的 `if not config.wecom_webhook_url: sys.exit(1)` 是**不可达死代码**（`load_config()` 已先抛），不能作为"现有逻辑已支持"的证据。
- wecom 改可选后，`news_pipeline.py:534` 与 `:906` 的 wecom 分支必须加"按配置守卫"：`config.wecom_webhook_url` 为空时跳过 wecom、走飞书，否则每轮 degraded。
- Telegram：`.env` 中 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` 留空 → `_has_telegram_delivery()` 返回 False，天然停用（此点成立）。
- 两者代码保留，随时可重新启用。

### 3.4 本轮范围声明

- **"推送不满 10 条"问题不在本轮范围**。条数瓶颈在 `_build_headline_items`（`news_pipeline.py:126-159`，只保留能与 selected 匹配的 LLM 输出项）和 LLM 返回的 headline_items 数量，需要单独分析，本轮不解决。
- 本轮只交付：ithome 占比修复 + 飞书通道 + 企微/Telegram 停用。

## 4. 测试策略

### 4.1 单元测试

| 文件 | 覆盖 |
|---|---|
| `tests/test_feishu_pusher.py` | mock httpx client：token 获取、卡片 payload、`code==0` 成功、`99991663` 重取重试、HTTP 错误、token 缓存 |
| `tests/test_feishu_card.py` | 卡片 JSON 结构（header/elements）、标题转义、链接、分类分组、一句话判断、github 项目段 |
| `tests/test_source_policy.py`（或既有测试） | feeds.yaml 中 ithome 解析后 `quality_weight==2.0`、`filter_profile==strict` |
| `tests/test_app_config.py` | 补充：`WECOM_WEBHOOK_URL` 现在可选（缺省不抛错）；仅配 feishu 时 `load_config()` 正常 |

### 4.2 回归

- 现有 `test_news_pipeline.py`、`test_wecom*`、`test_telegram*` 全绿，确认企微/Telegram 通道不破坏
- **关键回归**：仅配置飞书（不配 telegram、不配 wecom）时，pipeline 应走 `_deliver_with_pending` 的 feishu 分支，pending 文件在成功后删除、不产生 degraded 残留——需在 `test_news_pipeline.py` 补一条该场景的集成断言

### 4.3 真实跑通

改完后部署到远程，用一次真实推送验证交互卡片能发到飞书群（复用 `FEISHU_HOME_CHANNEL` 作为目标）。若 `FEISHU_HOME_CHANNEL` 实际是 open_id 而非 chat_id，`receive_id_type` 需相应调整。

## 5. 涉及文件

| 文件 | 改动 |
|---|---|
| `feeds.yaml` | ithome 补策略字段（部署时 rsync 上远程） |
| `pusher/feishu.py` | 新增，飞书发送器 |
| `app/renderers/feishu_card.py` | 新增，卡片渲染器 |
| `app/config.py` | 新增飞书配置字段；**`WECOM_WEBHOOK_URL` 从 required 改为可选** |
| `app/pipeline/news_pipeline.py` | 接入飞书通道：改触发条件（`:881`）、pending 恢复门禁（`:387`）、企微分支守卫（`:534`/`:906`）、`_build_pending_payload` 只写启用通道、新增 `_attempt_feishu` |
| `tests/test_feishu_pusher.py` | 新增 |
| `tests/test_feishu_card.py` | 新增 |
| `tests/test_app_config.py` | 补 wecom 可选断言 |
| `tests/test_news_pipeline.py` | 补"仅飞书"集成场景 |
| 源策略测试 | 补 ithome 断言 |
| `.env.example` | 补飞书配置说明 |

## 6. 边界与风险

- **不引入新依赖**：httpx 直连，避免 lark-oapi 体积
- **凭证安全**：`FeishuError` 消息不含 `app_secret`/token；`.env` 不入库（已有 `.gitignore`）；`_validate_secret_free`（`app/delivery/store.py:48-60`）只拦含 `token`/`chat_id` 键名，`feishu_card` 可安全落盘
- **复用同一机器人**：hermes 与 Claw_news 共用同一飞书应用。hermes 用 WebSocket 事件订阅，Claw_news 用 tenant_access_token 主动发送，两者不冲突（不同租户会话 token）
- **推送目标待验证**：`FEISHU_HOME_CHANNEL` 具体是 chat_id 还是 open_id 需跑通时确认，若是 open_id 则 `receive_id_type` 相应改为 `open_id`
- **错误告警通道失效**（审查发现）：若实现"飞书单通道"，`app/agents/news_agent.py:121` 的 wecom 错误告警也会失效。本轮将错误通知路径改为不依赖 wecom 或降级为日志，避免告警静默丢失
- **pending 污染风险**（审查发现）：若不改 `_build_pending_payload` 只写启用通道，Telegram 停用后每轮都会 degraded 且 pending 文件永不删除——此点已在 3.2.4 列为必改项
- **摘要内容转义**：`lark_md` content 中 `core_summary`/importance/trend 原样拼接，含 `**`/`[` 时卡片渲染可能异常。与企微现状一致，低风险，本轮不额外处理
- **无单源硬上限**：ithome 修复依赖软惩罚生效；若其他源彻底无候选，仍可能满额。本轮不引入硬上限
