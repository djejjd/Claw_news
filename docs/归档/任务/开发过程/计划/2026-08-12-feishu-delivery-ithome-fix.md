# 飞书推送通道 + IT之家来源权重修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 IT 之家来源权重失效（feeds.yaml 补策略字段），并新增飞书应用机器人推送通道，停用企微/Telegram。

**Architecture:** ithome 修复是纯配置改动（`feeds.yaml` 补 `quality_weight: 2.0 / filter_profile: strict / retention_hours: 24 / tier: fast_news`），无 Python 改动。飞书通道新增 `pusher/feishu.py`（httpx 直连拿 tenant_access_token + 发 interactive 卡片）+ `app/renderers/feishu_card.py`（复用 wecom 渲染逻辑），接入 `news_pipeline.py` 的 `_deliver_with_pending`，并修正该交付链路的三个阻断级缺陷：触发条件只认 telegram、`WECOM_WEBHOOK_URL` 是 required、wecom 分支无条件执行。

**Tech Stack:** Python 3.12 / httpx / pytest / 飞书 open API（`auth/v3/tenant_access_token/internal` + `im/v1/messages`）

## Global Constraints

- **中文文档优先**：代码注释、测试名、commit message 用中文；代码标识符保持英文。
- **分支隔离**：本计划在 `feature/feishu-delivery-ithome-fix` 分支执行，禁止在 `main` 上修改。
- **不引入新依赖**：httpx 直连飞书 API，不用 lark-oapi。
- **`WECOM_WEBHOOK_URL` 从 required 改为可选**：企微停用=不配置 webhook，代码保留。
- **凭证安全**：`FeishuError` 消息不得包含 `app_secret`/token；`.env` 不入库。
- **测试先行**：每个 Task 先写失败测试，再写最小实现，再验证通过。
- **每 Task 只提交自己的范围**，未经明确授权不得 commit。
- **spec 与本计划文件暂不提交**，与最终代码一起提交（用户已确认）。

---

### Task 1: feeds.yaml 补 ithome 策略字段

**Files:**
- Modify: `feeds.yaml:19-21`（tool 分类下 ithome 条目）
- Test: `tests/test_source_policy.py`（或新建 `tests/test_feeds_ithome_policy.py`）

**Interfaces:**
- Consumes: `collectors/ai_rss.py:130-133` `_load_yaml_feeds()` 已保留策略字段
- Produces: 无代码接口依赖；后续 Task 直接依赖 registry 生效

- [ ] **Step 1: 写失败测试**（新建 `tests/test_feeds_ithome_policy.py`）

```python
"""feeds.yaml 中 ithome 策略字段必须与内置降权一致，防止再次漂移。"""
import pytest

from collectors.ai_rss import load_feed_configuration
from app.content.source_policy import build_source_policy_registry


def _build_ithome_policy():
    feed_config = load_feed_configuration()
    assert feed_config is not None, "feeds.yaml 不存在或解析失败"
    feeds_raw = []
    for cat in ("ai", "tool", "game"):
        for f in feed_config.get("feeds", {}).get(cat, []):
            if isinstance(f, dict):
                feeds_raw.append({**f, "category": cat})
    registry = build_source_policy_registry(feeds_raw)
    return registry.get("ithome")


def test_ithome_has_reduced_quality_weight():
    policy = _build_ithome_policy()
    assert policy is not None, "feeds.yaml 中缺少 ithome 条目"
    assert policy.quality_weight == 2.0


def test_ithome_has_strict_filter():
    policy = _build_ithome_policy()
    assert policy is not None
    assert policy.filter_profile == "strict"


def test_ithome_retention_24h():
    policy = _build_ithome_policy()
    assert policy is not None
    assert policy.retention_hours == 24


def test_ithome_tier_fast_news():
    policy = _build_ithome_policy()
    assert policy is not None
    assert policy.tier == "fast_news"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `./venv/bin/pytest tests/test_feeds_ithome_policy.py -v`
Expected: FAIL（当前 `policy.quality_weight` 为默认 3.0，断言 2.0 失败）

- [ ] **Step 3: 修改 `feeds.yaml`**

当前（`feeds.yaml:19-21`）：
```yaml
    - url: https://www.ithome.com/rss/
      source: ithome
```
改为：
```yaml
    - url: https://www.ithome.com/rss/
      source: ithome
      tier: fast_news
      retention_hours: 24
      quality_weight: 2.0
      filter_profile: strict
```

- [ ] **Step 4: 运行测试验证通过**

Run: `./venv/bin/pytest tests/test_feeds_ithome_policy.py -v`
Expected: PASS（4 个断言全绿）

- [ ] **Step 5: 回归源策略测试**

Run: `./venv/bin/pytest tests/test_source_policy.py -v`
Expected: 全绿

---

### Task 2: `app/config.py` 新增飞书配置 + wecom 改可选

**Files:**
- Modify: `app/config.py`（`AppConfig` 数据类 + `load_config()`）
- Modify: `tests/test_app_config.py`（`test_missing_wecom_webhook_url` 改为 wecom 可选断言 + 新增飞书断言）
- Modify: `app/pipeline/news_pipeline.py` 新增 `_has_wecom_delivery` / `_has_feishu_delivery` 辅助（为 Task 4 做准备）

**Interfaces:**
- Produces:
  - `AppConfig` 新增字段：`feishu_app_id: str | None = None`, `feishu_app_secret: str | None = None`, `feishu_chat_id: str | None = None`
  - `AppConfig.wecom_webhook_url` 类型保持 `str`，`load_config()` 不再对它抛 ValueError（缺省为空字符串 `""`）
  - `news_pipeline.py` 新增函数：`_has_wecom_delivery(config) -> bool`、`_has_feishu_delivery(config) -> bool`

- [ ] **Step 1: 写失败测试**（在 `tests/test_app_config.py`）

先看现有 `test_missing_wecom_webhook_url`（`tests/test_app_config.py:41-47`），它断言缺 wecom 抛 `ValueError`。本 Task 后 wecom 变可选，该测试必须反转。

把 `test_missing_wecom_webhook_url` 改为：
```python
def test_wecom_webhook_optional(self, monkeypatch):
    """WECOM_WEBHOOK_URL 缺省时 wecom_webhook_url 为空字符串，不抛错。"""
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
    monkeypatch.delenv("WECOM_WEBHOOK_URL", raising=False)
    config = load_config()
    assert config.wecom_webhook_url == ""
```

新增飞书断言类：
```python
class TestFeishuConfig:
    def test_feishu_defaults_none(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
        config = load_config()
        assert config.feishu_app_id is None
        assert config.feishu_app_secret is None
        assert config.feishu_chat_id is None

    def test_feishu_partial_missing_raises(self, monkeypatch):
        """只配 app_id 不配 app_secret 时报错（与 telegram 配对校验一致）。"""
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
        monkeypatch.setenv("FEISHU_APP_ID", "cli_test")
        with pytest.raises(ValueError, match="FEISHU_APP_SECRET"):
            load_config()

    def test_feishu_full_config(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini")
        monkeypatch.setenv("FEISHU_APP_ID", "cli_test")
        monkeypatch.setenv("FEISHU_APP_SECRET", "secret_test")
        monkeypatch.setenv("FEISHU_CHAT_ID", "oc_test")
        config = load_config()
        assert config.feishu_app_id == "cli_test"
        assert config.feishu_app_secret == "secret_test"
        assert config.feishu_chat_id == "oc_test"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `./venv/bin/pytest tests/test_app_config.py -v`
Expected: FAIL（`test_feishu_*` 因 `AppConfig` 无这些字段报 `AttributeError`；`test_wecom_webhook_optional` 因仍抛 `ValueError` 失败）

- [ ] **Step 3: 改 `app/config.py`**

`AppConfig` 数据类（`app/config.py:10-20`）新增字段：
```python
    feishu_app_id: str | None = None
    feishu_app_secret: str | None = None
    feishu_chat_id: str | None = None
```

`__repr__`（`app/config.py:22-31`）末尾追加掩码字段：
```python
            f"feishu_app_id={'***' if self.feishu_app_id else None!r}, "
            f"feishu_app_secret={'***' if self.feishu_app_secret else None!r}, "
            f"feishu_chat_id={'***' if self.feishu_chat_id else None!r})"
```

`load_config()`（`app/config.py:40-48`）把 `WECOM_WEBHOOK_URL` 从 required dict 移除：
```python
    required = {
        "LLM_API_KEY": os.getenv("LLM_API_KEY", "").strip(),
        "LLM_BASE_URL": os.getenv("LLM_BASE_URL", "").strip(),
        "LLM_MODEL": os.getenv("LLM_MODEL", "").strip(),
    }
```

在 Telegram 配对校验（`app/config.py:61-64`）之后新增飞书配对校验：
```python
    feishu_app_id = os.getenv("FEISHU_APP_ID", "").strip() or None
    feishu_app_secret = os.getenv("FEISHU_APP_SECRET", "").strip() or None
    feishu_chat_id = os.getenv("FEISHU_CHAT_ID", "").strip() or None
    if feishu_app_id and not feishu_app_secret:
        raise ValueError("missing required paired environment variable: FEISHU_APP_SECRET")
    if feishu_app_secret and not feishu_app_id:
        raise ValueError("missing required paired environment variable: FEISHU_APP_ID")
    if feishu_chat_id and not (feishu_app_id and feishu_app_secret):
        raise ValueError("FEISHU_CHAT_ID requires FEISHU_APP_ID and FEISHU_APP_SECRET")
```

`AppConfig(...)` 构造（`app/config.py:66-76`）追加：
```python
        feishu_app_id=feishu_app_id,
        feishu_app_secret=feishu_app_secret,
        feishu_chat_id=feishu_chat_id,
```

- [ ] **Step 4: 在 `news_pipeline.py` 新增 `_has_wecom_delivery` / `_has_feishu_delivery`**

在 `_has_telegram_delivery`（`news_pipeline.py:96-100`）旁边新增：
```python
def _has_wecom_delivery(config) -> bool:
    return bool(_config_string(config, "wecom_webhook_url"))


def _has_feishu_delivery(config) -> bool:
    return bool(
        _config_string(config, "feishu_app_id")
        and _config_string(config, "feishu_app_secret")
        and _config_string(config, "feishu_chat_id")
    )
```

- [ ] **Step 5: 运行测试验证通过**

Run: `./venv/bin/pytest tests/test_app_config.py -v`
Expected: PASS（含反转后的 wecom 可选断言 + 3 个飞书断言）

- [ ] **Step 6: 回归其余配置测试**

Run: `./venv/bin/pytest tests/test_app_config.py tests/test_news_pipeline.py -v`
Expected: 全绿（`test_news_pipeline.py` 若因 wecom required 假设失败，需先看其 fixture——若它显式 setenv wecom 则不受影响）

---

### Task 3: 新增 `pusher/feishu.py` 飞书发送器

**Files:**
- Create: `pusher/feishu.py`
- Test: `tests/test_feishu_pusher.py`

**Interfaces:**
- Consumes: `config.feishu_app_id` / `config.feishu_app_secret` / `config.feishu_chat_id`
- Produces:
  - `class FeishuError(RuntimeError)`
  - `@dataclass(frozen=True) class FeishuPushResult: messages_sent: int`
  - `class FeishuPusher`:
    - `__init__(self, app_id: str, app_secret: str, chat_id: str, client: httpx.AsyncClient | None = None)`
    - `async def push_card(self, card: dict) -> FeishuPushResult`

- [ ] **Step 1: 写失败测试**（新建 `tests/test_feishu_pusher.py`）

```python
"""FeishuPusher 单元测试：mock httpx client，不触发真实网络。"""
import json

import httpx
import pytest

from pusher.feishu import FeishuError, FeishuPusher

_APP_ID = "cli_test"
_APP_SECRET = "secret_test"
_CHAT_ID = "oc_test"


def _mock_transport(routes):
    """routes: list[(method, url_partial, status, json)] 按顺序消费。"""
    responses = []
    for method, url_partial, status, body in routes:
        def _handler(request):
            if url_partial not in str(request.url):
                return httpx.Response(500, json={"code": -1, "msg": "unexpected url"})
            return httpx.Response(status, json=body)
        responses.append(_handler)

    def _dispatch(request):
        return responses.pop(0)(request)

    return httpx.MockTransport(_dispatch)


def _client(routes):
    transport = _mock_transport(routes)
    return httpx.AsyncClient(transport=transport)


async def test_push_card_success():
    token_resp = {"code": 0, "tenant_access_token": "t-abc", "expire": 7200}
    msg_resp = {"code": 0, "msg": "success"}
    client = _client([
        ("POST", "/auth/v3/tenant_access_token/internal", 200, token_resp),
        ("POST", "/im/v1/messages", 200, msg_resp),
    ])
    pusher = FeishuPusher(_APP_ID, _APP_SECRET, _CHAT_ID, client=client)
    result = await pusher.push_card({"config": {}, "elements": []})
    assert result.messages_sent == 1


async def test_push_card_requests_token_with_credentials():
    captured = {}

    def _handler(request):
        captured["body"] = json.loads(request.content)
        captured["url"] = str(request.url)
        if "/auth/v3/tenant_access_token" in str(request.url):
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "t-abc", "expire": 7200})
        return httpx.Response(200, json={"code": 0})

    client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
    pusher = FeishuPusher(_APP_ID, _APP_SECRET, _CHAT_ID, client=client)
    await pusher.push_card({"config": {}, "elements": []})
    assert captured["body"]["app_id"] == _APP_ID
    assert captured["body"]["app_secret"] == _APP_SECRET


async def test_push_card_sends_interactive_message():
    captured = {}

    def _handler(request):
        if "/auth/v3/tenant_access_token" in str(request.url):
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "t-abc", "expire": 7200})
        captured["body"] = json.loads(request.content)
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"code": 0})

    client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
    card = {"config": {"wide_screen_mode": True}, "elements": [{"tag": "div"}]}
    pusher = FeishuPusher(_APP_ID, _APP_SECRET, _CHAT_ID, client=client)
    await pusher.push_card(card)
    assert "receive_id_type=chat_id" in captured["url"]
    assert captured["body"]["receive_id"] == _CHAT_ID
    assert captured["body"]["msg_type"] == "interactive"
    assert json.loads(captured["body"]["content"]) == card


async def test_push_card_invalid_token_retries_once():
    """code==99991663（token 无效）时重取 token 后重试一次。"""
    calls = []

    def _handler(request):
        if "/auth/v3/tenant_access_token" in str(request.url):
            calls.append("token")
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "t-abc", "expire": 7200})
        calls.append("msg")
        if calls.count("msg") == 1:
            return httpx.Response(200, json={"code": 99991663, "msg": "token invalid"})
        return httpx.Response(200, json={"code": 0})

    client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
    pusher = FeishuPusher(_APP_ID, _APP_SECRET, _CHAT_ID, client=client)
    result = await pusher.push_card({"config": {}, "elements": []})
    assert result.messages_sent == 1
    assert calls.count("token") == 2


async def test_push_card_api_error_raises():
    client = _client([
        ("POST", "/auth/v3/tenant_access_token/internal", 200, {"code": 0, "tenant_access_token": "t", "expire": 7200}),
        ("POST", "/im/v1/messages", 200, {"code": 99991400, "msg": "bad request"}),
    ])
    pusher = FeishuPusher(_APP_ID, _APP_SECRET, _CHAT_ID, client=client)
    with pytest.raises(FeishuError, match="99991400"):
        await pusher.push_card({"config": {}, "elements": []})


async def test_push_card_http_error_raises():
    client = _client([
        ("POST", "/auth/v3/tenant_access_token/internal", 200, {"code": 0, "tenant_access_token": "t", "expire": 7200}),
        ("POST", "/im/v1/messages", 500, {"code": -1}),
    ])
    pusher = FeishuPusher(_APP_ID, _APP_SECRET, _CHAT_ID, client=client)
    with pytest.raises(FeishuError, match="feishu_http"):
        await pusher.push_card({"config": {}, "elements": []})


async def test_error_message_contains_no_secret():
    """FeishuError 消息不得包含 app_secret 或 token。"""
    client = _client([
        ("POST", "/auth/v3/tenant_access_token/internal", 200, {"code": 0, "tenant_access_token": "t", "expire": 7200}),
        ("POST", "/im/v1/messages", 200, {"code": 99991400, "msg": "bad"}),
    ])
    pusher = FeishuPusher(_APP_ID, _APP_SECRET, _CHAT_ID, client=client)
    with pytest.raises(FeishuError) as exc_info:
        await pusher.push_card({"config": {}, "elements": []})
    assert _APP_SECRET not in str(exc_info.value)
    assert "t-abc" not in str(exc_info.value)
```

- [ ] **Step 2: 运行测试验证失败**

Run: `./venv/bin/pytest tests/test_feishu_pusher.py -v`
Expected: FAIL（`pusher/feishu.py` 不存在，`ModuleNotFoundError`）

- [ ] **Step 3: 写 `pusher/feishu.py`**

```python
"""飞书应用机器人推送器 — httpx 直连，不引 lark-oapi。

流程：
1. POST /open-apis/auth/v3/tenant_access_token/internal 取 tenant_access_token（缓存）
2. POST /open-apis/im/v1/messages?receive_id_type=chat_id 发 interactive 卡片
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from time import monotonic

import httpx

_API_BASE_URL = "https://open.feishu.cn"
_TOKEN_URL = f"{_API_BASE_URL}/open-apis/auth/v3/tenant_access_token/internal"
_MESSAGE_URL = f"{_API_BASE_URL}/open-apis/im/v1/messages"
_TOKEN_EXPIRY_MARGIN = 300  # 提前 300 秒过期，避免临界失效
_TOKEN_INVALID_CODE = 99991663


class FeishuError(RuntimeError):
    """一个不含密钥的飞书交付失败。"""


@dataclass(frozen=True)
class FeishuPushResult:
    messages_sent: int


class FeishuPusher:
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        chat_id: str,
        client: httpx.AsyncClient | None = None,
    ):
        self._app_id = app_id
        self._app_secret = app_secret
        self._chat_id = chat_id
        self._client = client
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    async def push_card(self, card: dict) -> FeishuPushResult:
        client = self._client or httpx.AsyncClient()
        try:
            token = await self._get_valid_token(client)
            content = json.dumps(card, ensure_ascii=False)
            resp = await client.post(
                _MESSAGE_URL,
                params={"receive_id_type": "chat_id"},
                json={"receive_id": self._chat_id, "msg_type": "interactive", "content": content},
                timeout=15.0,
            )
            body = _response_body(resp)
            if body is not None and body.get("code") == _TOKEN_INVALID_CODE:
                # token 失效：重取后重试一次
                self._token = None
                token = await self._get_valid_token(client)
                resp = await client.post(
                    _MESSAGE_URL,
                    params={"receive_id_type": "chat_id"},
                    json={"receive_id": self._chat_id, "msg_type": "interactive", "content": content},
                    timeout=15.0,
                )
                body = _response_body(resp)
            _check_ok(resp, body)
            return FeishuPushResult(messages_sent=1)
        finally:
            if self._client is None:
                await client.aclose()

    # ---- Internal ----

    async def _get_valid_token(self, client: httpx.AsyncClient) -> str:
        if self._token and monotonic() < self._token_expires_at:
            return self._token
        try:
            resp = await client.post(
                _TOKEN_URL,
                json={"app_id": self._app_id, "app_secret": self._app_secret},
                timeout=15.0,
            )
        except httpx.HTTPError as exc:
            raise FeishuError(f"feishu_transport: {type(exc).__name__}") from exc
        body = _response_body(resp)
        _check_ok(resp, body)
        if not body:
            raise FeishuError("feishu_token: invalid_json")
        token = body.get("tenant_access_token")
        if not isinstance(token, str) or not token:
            raise FeishuError("feishu_token: missing_token")
        expire = body.get("expire")
        self._token = token
        self._token_expires_at = monotonic() + max(int(expire or 0) - _TOKEN_EXPIRY_MARGIN, 60)
        return token


def _check_ok(resp: httpx.Response, body: dict | None) -> None:
    if resp.is_error:
        raise FeishuError(f"feishu_http: {resp.status_code}")
    if body is None:
        raise FeishuError("feishu_response: invalid_json")
    code = body.get("code")
    if code != 0:
        raise FeishuError(f"feishu_api: {code}")


def _response_body(response: httpx.Response) -> dict | None:
    try:
        body = response.json()
    except ValueError:
        return None
    return body if isinstance(body, dict) else None
```

- [ ] **Step 4: 运行测试验证通过**

Run: `./venv/bin/pytest tests/test_feishu_pusher.py -v`
Expected: PASS（7 个测试全绿）

- [ ] **Step 5: Lint 检查**

Run: `./venv/bin/ruff check pusher/feishu.py && ./venv/bin/ruff format --check pusher/feishu.py`
Expected: 通过

---

### Task 4: 新增 `app/renderers/feishu_card.py` 卡片渲染器

**Files:**
- Create: `app/renderers/feishu_card.py`
- Test: `tests/test_feishu_card.py`

**Interfaces:**
- Consumes:
  - `app.tools.summary_result.SummaryResult`（`headline_items` 为 `SummaryItem` 列表）
  - `app.renderers.wecom_markdown._escape_title` / `_source_display` / `MAX_DIGEST_ITEMS` / `DISPLAY_CATEGORY_ORDER`
- Produces:
  - `def render_feishu_card(result: SummaryResult, github_items: list | None = None, pushed_urls: set[str] | None = None, github_recommendations: dict[str, str] | None = None) -> dict` — 返回飞书 interactive 卡片 dict

- [ ] **Step 1: 写失败测试**（新建 `tests/test_feishu_card.py`）

参考 `tests/test_wecom_markdown_renderer.py` 的 `make_item`/`make_result` fixture 模式：

```python
"""render_feishu_card 单元测试。"""
from app.renderers.feishu_card import render_feishu_card
from app.tools.summary_result import SummaryItem, SummaryResult


def make_item(
    title="GPT-5 发布",
    url="https://example.com/gpt5",
    core_summary="OpenAI 推出新一代模型。",
    importance="高",
    trend="上升",
    source="qbitai",
    display_category="AI",
    topic_label=None,
):
    return SummaryItem(
        title=title,
        url=url,
        core_summary=core_summary,
        importance=importance,
        trend=trend,
        source=source,
        display_category=display_category,
        topic_label=topic_label,
    )


def make_result(items=None, daily_judgement="今天 AI 领域动作频频。"):
    return SummaryResult(headline_items=items or [], daily_judgement=daily_judgement)


def test_header_present():
    card = render_feishu_card(make_result([make_item()]))
    assert card["header"]["title"]["content"] == "AI / 游戏 / 工具 热点"
    assert card["config"]["wide_screen_mode"] is True


def test_element_contains_title_and_link():
    card = render_feishu_card(make_result([make_item(title="GPT-5 发布", url="https://x.com/1")]))
    text = "".join(e["text"]["content"] for e in card["elements"] if e["tag"] == "div")
    assert "GPT-5 发布" in text
    assert "https://x.com/1" in text


def test_contains_core_summary_and_source():
    card = render_feishu_card(make_result([make_item(core_summary="OpenAI 发布模型。")]))
    text = "".join(e["text"]["content"] for e in card["elements"] if e["tag"] == "div")
    assert "OpenAI 发布模型。" in text
    assert "量子位" in text  # qbitai → 量子位 · 国内


def test_daily_judgement_in_note():
    card = render_feishu_card(make_result([make_item()], daily_judgement="AI 行业波澜不惊。"))
    notes = [e for e in card["elements"] if e["tag"] == "note"]
    assert any("AI 行业波澜不惊" in json_str(n) for n in notes)


def test_title_markdown_escaped():
    """标题中的 * 和 [ 必须转义，防止破坏 lark_md。"""
    card = render_feishu_card(make_result([make_item(title="真*标题[测试]")]))
    text = "".join(e["text"]["content"] for e in card["elements"] if e["tag"] == "div")
    assert "真\\*标题\\[测试\\]" in text


def test_no_items_still_has_header_and_judgement():
    card = render_feishu_card(make_result([], daily_judgement="今日无内容。"))
    assert card["header"]["title"]["content"] == "AI / 游戏 / 工具 热点"
    assert any("今日无内容" in json_str(n) for n in card["elements"] if n["tag"] == "note")


def test_github_items_rendered():
    """github_items 渲染为"今日值得看项目"段。"""
    from types import SimpleNamespace

    gh = SimpleNamespace(full_name="anthropics/claude-code", url="https://x.com/r", stars=5000, language="Python", description="AI 工具")
    card = render_feishu_card(make_result([make_item()]), github_items=[gh], github_recommendations={"anthropics/claude-code": "值得关注"})
    text = "".join(e["text"]["content"] for e in card["elements"] if e["tag"] == "div")
    assert "anthropics/claude-code" in text
    assert "值得关注" in text


def json_str(element):
    import json
    return json.dumps(element, ensure_ascii=False)
```

- [ ] **Step 2: 运行测试验证失败**

Run: `./venv/bin/pytest tests/test_feishu_card.py -v`
Expected: FAIL（`app/renderers/feishu_card.py` 不存在，`ModuleNotFoundError`）

- [ ] **Step 3: 写 `app/renderers/feishu_card.py`**

```python
"""飞书交互卡片渲染器 — 把日报 SummaryResult 映射为飞书 interactive 卡片。

复用 wecom_markdown 的转义与来源标签逻辑，避免重复。
"""

from __future__ import annotations

from collections import OrderedDict

from app.renderers.wecom_markdown import (
    DISPLAY_CATEGORY_ORDER,
    MAX_DIGEST_ITEMS,
    _escape_title,
    _source_display,
)
from app.tools.summary_result import SummaryResult

_CARD_TITLE = "AI / 游戏 / 工具 热点"


def render_feishu_card(
    result: SummaryResult,
    github_items: list | None = None,
    pushed_urls: set[str] | None = None,
    github_recommendations: dict[str, str] | None = None,
) -> dict:
    """把 *result* 渲染为飞书 interactive 卡片 dict。"""
    elements: list[dict] = []
    items = (result.headline_items or [])[:MAX_DIGEST_ITEMS]
    grouped_items: OrderedDict[str, list] = OrderedDict(
        (category, []) for category in DISPLAY_CATEGORY_ORDER
    )
    for item in items:
        category = item.display_category if item.display_category in grouped_items else "AI"
        grouped_items[category].append(item)

    for category, category_items in grouped_items.items():
        if not category_items:
            continue
        lines = [f"**【{category}】{len(category_items)}**"]
        for item in category_items:
            safe_title = _escape_title(item.title)
            url = item.url or ""
            topic_label = f"[{item.topic_label}] " if item.topic_label else ""
            is_new = "新" if pushed_urls is None or url not in pushed_urls else "续"
            marker = f"[{is_new}] "
            if url:
                lines.append(f"**{len([l for l in lines if l])}.** {topic_label}{marker}[{safe_title}]({url})")
            else:
                lines.append(f"**{len([l for l in lines if l])}.** {topic_label}{marker}{safe_title}")
            source_display = _source_display(item.source) if item.source else ""
            lines.append(
                f"> {item.core_summary} | 重要性：{item.importance} | "
                f"趋势：{item.trend} — {source_display}"
            )
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}})
        elements.append({"tag": "hr"})

    # 去掉最后一个多余分隔线
    if elements and elements[-1]["tag"] == "hr":
        elements.pop()

    if github_items:
        lines = ["**今日值得看项目**"]
        for i, item in enumerate(github_items[:3], 1):
            language = f" · {item.language}" if item.language else ""
            description = item.description or "暂无简介"
            reason = (github_recommendations or {}).get(item.full_name, "")
            reason_line = f" | 💡 {reason}" if reason else ""
            lines.append(f"**{i}.** [{item.full_name}]({item.url})")
            lines.append(f"> {description}")
            lines.append(f"> ⭐ {item.stars}{language}{reason_line}")
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}})
        elements.append({"tag": "hr"})

    if result.daily_judgement:
        elements.append(
            {
                "tag": "note",
                "elements": [{"tag": "plain_text", "content": f"今日一句话判断：{result.daily_judgement}"}],
            }
        )

    return {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "content": _CARD_TITLE}, "template": "blue"},
        "elements": elements,
    }
```

- [ ] **Step 4: 运行测试验证通过**

Run: `./venv/bin/pytest tests/test_feishu_card.py -v`
Expected: PASS（8 个测试全绿）

- [ ] **Step 5: Lint 检查**

Run: `./venv/bin/ruff check app/renderers/feishu_card.py && ./venv/bin/ruff format --check app/renderers/feishu_card.py`
Expected: 通过

---

### Task 5: `news_pipeline.py` 接入飞书通道

**Files:**
- Modify: `app/pipeline/news_pipeline.py`
  - 触发条件（`news_pipeline.py:633` `run_pipeline` 内 pending 加载门禁）
  - 触发条件（`news_pipeline.py:881` `if _has_telegram_delivery(config): return await _deliver_with_pending(...)`）
  - pending 恢复门禁（`news_pipeline.py:387` `if not _has_telegram_delivery(config):`）
  - `_deliver_with_pending` 内 wecom 分支（`news_pipeline.py:534`）改按配置守卫
  - `_resume_pending_delivery` 内 wecom 分支（`news_pipeline.py:407-416`）改按配置守卫 + 新增 feishu 分支
  - `_build_pending_payload`（`news_pipeline.py:202-251`）只写启用通道 + 携带 feishu_card
  - 渲染调用处（`news_pipeline.py:841-852` 附近）新增 `render_feishu_card` 调用
  - 新增 `_attempt_feishu`（与 `_attempt_wecom` 同构）
- Test: `tests/test_news_pipeline.py`（新增"仅飞书"集成场景）

**Interfaces:**
- Consumes: `pusher/feishu.FeishuPusher` / `FeishuError`、`app.renderers.feishu_card.render_feishu_card`、`news_pipeline._has_feishu_delivery`、`news_pipeline._has_wecom_delivery`
- Produces: 无对外新接口；`run_pipeline` 在仅飞书配置下正确走 `_deliver_with_pending` 并清理 pending

- [ ] **Step 1: 写失败测试（聚焦交付决策层，新建 `tests/test_feishu_delivery_integration.py`）**

> 说明：`test_news_pipeline.py` 是纯契约测试、无网络 mock 链。`_deliver_with_pending` 和 `_build_pending_payload` 是 pipeline 内的模块级函数，直接在测试文件内 import，用 `tmp_path` 构造 stores、用简单 `SimpleNamespace` 构造 config，避开真实网络与 LLM。

```python
"""交付决策层测试：仅飞书配置时走 feishu 分支，pending 文件成功后删除。"""
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.pipeline.context import RunContext
from app.pipeline import news_pipeline as np


def make_ctx():
    return RunContext(
        trigger_mode="scheduler",
        period="morning",
        time_window_start="2026-08-12T00:00:00",
        time_window_end="2026-08-12T08:00:00",
    )


def make_config(**overrides):
    """wecom 空、telegram 空、feishu 有值的最小 config。"""
    base = {
        "wecom_webhook_url": "",
        "telegram_bot_token": None,
        "telegram_chat_id": None,
        "telegram_proxy": None,
        "feishu_app_id": "cli_test",
        "feishu_app_secret": "secret_test",
        "feishu_chat_id": "oc_test",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def make_stores(tmp_path: Path):
    np._DATA_DIR = tmp_path  # 重定向 data 目录到临时目录
    return {
        "state_store": __import__("app.storage.state_store", fromlist=["StateStore"]).StateStore(tmp_path),
        "metrics_store": __import__(
            "app.storage.source_metrics_store", fromlist=["SourceMetricsStore"]
        ).SourceMetricsStore(tmp_path),
        "exposure_store": __import__(
            "app.storage.github_exposure_store", fromlist=["GitHubExposureStore"]
        ).GitHubExposureStore(tmp_path),
    }


def test_build_pending_payload_feishu_only(tmp_path):
    """仅飞书时 _build_pending_payload 只写 feishu 通道，不写 wecom/telegram。"""
    np._DATA_DIR = tmp_path
    payload = np._build_pending_payload(
        ctx=make_ctx(),
        markdown="# 热点",
        telegram_messages=[],
        feishu_card={"config": {}, "elements": []},
        config=make_config(),
        selected_count=3,
        daily_judgement="今日动作频频。",
        source_failures=[],
        headline_payload=[],
        github_ranked=[],
        github_recommendations={},
        published_urls=[],
        published_keys=[],
        selection_evidence=[],
        relevance_rejected=[],
        selected_counts_by_source={},
        metric_rows=[],
    )
    assert "feishu" in payload["channels"]
    assert "wecom" not in payload["channels"]
    assert "telegram" not in payload["channels"]
    assert "feishu_card" in payload["messages"]


def test_build_pending_payload_wecom_and_feishu(tmp_path):
    """wecom + feishu 双配置时两个通道都写入。"""
    np._DATA_DIR = tmp_path
    payload = np._build_pending_payload(
        ctx=make_ctx(),
        markdown="# 热点",
        telegram_messages=[],
        feishu_card={"config": {}, "elements": []},
        config=make_config(wecom_webhook_url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=x"),
        selected_count=3,
        daily_judgement="",
        source_failures=[],
        headline_payload=[],
        github_ranked=[],
        github_recommendations={},
        published_urls=[],
        published_keys=[],
        selection_evidence=[],
        relevance_rejected=[],
        selected_counts_by_source={},
        metric_rows=[],
    )
    assert "wecom" in payload["channels"]
    assert "feishu" in payload["channels"]
    assert "telegram" not in payload["channels"]


def test_deliver_with_pending_feishu_only_success(tmp_path, monkeypatch):
    """仅飞书时 _deliver_with_pending 走 feishu 分支，status=ok、pending 文件删除。"""
    async def fake_attempt_feishu(card, app_id, app_secret, chat_id):
        return True, None

    async def fake_attempt_wecom(markdown, url):
        raise AssertionError("wecom 不应被调用（wecom 停用）")

    monkeypatch.setattr(np, "_attempt_feishu", fake_attempt_feishu)
    monkeypatch.setattr(np, "_attempt_wecom", fake_attempt_wecom)
    # _finalize_delivery 需要 state_store/metrics 真实可写，用 tmp_path
    stores = make_stores(tmp_path)

    result = asyncio.run(
        np._deliver_with_pending(
            ctx=make_ctx(),
            config=make_config(),
            markdown="# 热点",
            telegram_messages=[],
            feishu_card={"config": {}, "elements": []},
            selected_count=3,
            daily_judgement="今日动作频频。",
            source_failures=[],
            headline_payload=[],
            github_ranked=[],
            github_recommendations={},
            published_urls=["https://x.com/1"],
            published_keys=["www.x.com/1"],
            selection_evidence=[],
            relevance_rejected=[],
            selected_counts_by_source={"qbitai": 3},
            metric_rows=[],
            state_store=stores["state_store"],
            metrics_store=stores["metrics_store"],
            exposure_store=stores["exposure_store"],
        )
    )
    assert result.status == "ok"
    assert result.pushed is True
    # pending 文件应已删除（全成功分支）
    pending_dir = tmp_path / "pending_deliveries"
    assert not list(pending_dir.glob("2026-08-12-morning.json")) if pending_dir.exists() else True
```

- [ ] **Step 2: 运行测试验证失败**

Run: `./venv/bin/pytest tests/test_feishu_delivery_integration.py -v`
Expected: FAIL
- `test_build_pending_payload_*`：`_build_pending_payload` 尚无 `feishu_card`/`config` 参数，报 `TypeError`
- `test_deliver_with_pending_feishu_only_success`：`_deliver_with_pending` 尚无 `feishu_card` 参数、无 `_attempt_feishu`，报 `TypeError`/`AttributeError`

- [ ] **Step 3: 读现状确认接线点**

阅读 `news_pipeline.py`：
- 第 96-100 行：`_has_telegram_delivery`
- 第 387 行：`_resume_pending_delivery` 内 telegram 门禁
- 第 534 行：`_deliver_with_pending` 内 wecom 无条件分支
- 第 407-416 行：`_resume_pending_delivery` 内 wecom 分支
- 第 633 行：`run_pipeline` 内 pending 加载门禁
- 第 881 行：`_deliver_with_pending` 调用门禁
- 第 841-852 行：渲染调用处

- [ ] **Step 4: 改 `_build_pending_payload` 只写启用通道**

`_build_pending_payload`（`news_pipeline.py:202-251`）签名新增 `feishu_card: dict` 与 `config` 两个参数，`messages` 与 `channels` 按配置只写启用通道。**改动的函数体开头部分**（替换现有 `messages`/`channels` 两个 dict 字面量）：

```python
def _build_pending_payload(
    *,
    ctx: RunContext,
    markdown: str,
    telegram_messages: list[str],
    feishu_card: dict,
    config,
    selected_count: int,
    # ↓ 以下参数保持现状不变：daily_judgement、source_failures、
    #   headline_payload、github_ranked、github_recommendations、
    #   published_urls、published_keys、selection_evidence、
    #   relevance_rejected、selected_counts_by_source、metric_rows
) -> dict:
    date = ctx.time_window_start[:10]
    delivery_id = make_delivery_id(date, ctx.period, markdown)
    messages: dict[str, object] = {}
    channels: dict[str, dict] = {}
    if _has_wecom_delivery(config):
        messages["wecom_markdown"] = markdown
        channels["wecom"] = _make_channel_payload(True, "pending")
    if _has_telegram_delivery(config):
        messages["telegram_messages"] = telegram_messages
        channels["telegram"] = _make_channel_payload(True, "pending")
    if _has_feishu_delivery(config):
        messages["feishu_card"] = feishu_card
        channels["feishu"] = _make_channel_payload(True, "pending")
    # ↓ return 语句保持现有 finalization 结构不变，仅 messages/channels 用上面的新 dict
```

同时把 `_resume_pending_delivery` 里 `pending_payload["messages"]["wecom_markdown"]`（`news_pipeline.py:397,405`）改为 `pending_payload["messages"].get("wecom_markdown", "")` 以兼容仅飞书 payload。

- [ ] **Step 5: 新增 `_attempt_feishu`**

在 `_attempt_wecom`（`news_pipeline.py:277-284`）后新增：

```python
async def _attempt_feishu(
    card: dict, app_id: str, app_secret: str, chat_id: str
) -> tuple[bool, str | None]:
    try:
        await FeishuPusher(app_id, app_secret, chat_id).push_card(card)
    except FeishuError as exc:
        return False, str(exc)
    except Exception as exc:
        return False, f"feishu_push: {type(exc).__name__}"
    return True, None
```

（需在文件顶部 import：`from pusher.feishu import FeishuError, FeishuPusher`）

- [ ] **Step 6: 改 `_deliver_with_pending` 内 wecom/feishu 分支**

`_deliver_with_pending` 的 wecom 分支（`news_pipeline.py:534-542`）改为按配置守卫 + 新增 feishu 分支：

```python
    errors: list[str] = []
    wecom_ok = False
    wecom_error = None
    if _has_wecom_delivery(config):
        wecom_ok, wecom_error = await _attempt_wecom(markdown, config.wecom_webhook_url)
        _update_pending_channel(
            pending_payload, "wecom", "succeeded" if wecom_ok else "failed", wecom_error
        )
        if not wecom_ok and wecom_error:
            errors.append(wecom_error)
        try:
            pending_store.save(ctx.time_window_start[:10], ctx.period, pending_payload)
        except Exception as exc:
            errors.append(f"pending_write_failed: {exc}")

    feishu_ok = False
    feishu_error = None
    if _has_feishu_delivery(config):
        feishu_ok, feishu_error = await _attempt_feishu(
            feishu_card, config.feishu_app_id, config.feishu_app_secret, config.feishu_chat_id
        )
        _update_pending_channel(
            pending_payload, "feishu", "succeeded" if feishu_ok else "failed", feishu_error
        )
        if not feishu_ok and feishu_error:
            errors.append(feishu_error)
        try:
            pending_store.save(ctx.time_window_start[:10], ctx.period, pending_payload)
        except Exception as exc:
            errors.append(f"pending_write_failed: {exc}")
```

注意 `_deliver_with_pending` 签名（`news_pipeline.py:478-499`）需新增 `feishu_card: dict` 参数。后续 `any_succeeded` / `pushed` 判定从 `bool(wecom_ok or telegram_ok)` 改为 `bool(wecom_ok or telegram_ok or feishu_ok)`（`news_pipeline.py:570,575`）。

- [ ] **Step 7: 改 `_resume_pending_delivery` 门禁 + feishu 分支**

`_resume_pending_delivery` 内 telegram 门禁（`news_pipeline.py:387-399`）改为同时认飞书。把现有 `if not _has_telegram_delivery(config): errors = ["telegram_config_missing"]` 块替换为：

```python
    if not (_has_feishu_delivery(config) or _has_telegram_delivery(config)):
        errors = ["delivery_config_missing"]
        _write_publish_status(_make_publish_status("failed", 0, False, errors))
        return PublishResult(
            status="failed",
            selected_count=len(pending_payload["finalization"]["published_urls"]),
            pushed=False,
            message_type="markdown",
            summary_preview=make_preview(pending_payload["messages"].get("wecom_markdown", "")),
            errors=errors,
        )
```

wecom/telegram/feishu 三个分支（`news_pipeline.py:407-429`）替换为（每个分支都加配置守卫 + `messages.get` 容错）：

```python
    if delivery_state.can_attempt("wecom") and _has_wecom_delivery(config):
        ok, error = await _attempt_wecom(messages.get("wecom_markdown", ""), config.wecom_webhook_url)
        _update_pending_channel(pending_payload, "wecom", "succeeded" if ok else "failed", error)
        if not ok and error:
            errors.append(error)
    if delivery_state.can_attempt("telegram") and _has_telegram_delivery(config):
        ok, error = await _attempt_telegram(
            messages.get("telegram_messages", []),
            config.telegram_bot_token,
            config.telegram_chat_id,
            proxy=config.telegram_proxy,
        )
        _update_pending_channel(pending_payload, "telegram", "succeeded" if ok else "failed", error)
        if not ok and error:
            errors.append(error)
    if delivery_state.can_attempt("feishu") and _has_feishu_delivery(config):
        ok, error = await _attempt_feishu(
            messages.get("feishu_card", {}),
            config.feishu_app_id,
            config.feishu_app_secret,
            config.feishu_chat_id,
        )
        _update_pending_channel(pending_payload, "feishu", "succeeded" if ok else "failed", error)
        if not ok and error:
            errors.append(error)
```

- [ ] **Step 8: 改 `run_pipeline` 两处门禁 + 渲染调用**

- `run_pipeline` 内 pending 加载门禁（`news_pipeline.py:633`）：
  `if _has_telegram_delivery(config):` → `if _has_feishu_delivery(config) or _has_telegram_delivery(config):`
- `_deliver_with_pending` 调用门禁（`news_pipeline.py:881`）：
  `if _has_telegram_delivery(config):` → `if _has_feishu_delivery(config) or _has_telegram_delivery(config):`
- 在 `render_digest` / `render_telegram_digest` 调用处（`news_pipeline.py:841-852`）新增：
  ```python
  feishu_card = render_feishu_card(
      summary,
      github_items=github_top3,
      github_recommendations=github_recommendations,
      pushed_urls=pushed_urls,
  )
  ```
  并在 `_deliver_with_pending(...)` 调用处传入 `feishu_card=feishu_card`。
- 文件顶部 import 新增：`from app.renderers.feishu_card import render_feishu_card`

- [ ] **Step 9: 运行测试验证通过**

Run: `./venv/bin/pytest tests/test_news_pipeline.py -v`
Expected: 全绿（含新增仅飞书场景）

- [ ] **Step 10: 全量回归**

Run: `./venv/bin/pytest -v`
Expected: 全绿

- [ ] **Step 11: Lint + 格式**

Run: `./venv/bin/ruff check . && ./venv/bin/ruff format --check .`
Expected: 通过

---

### Task 6: `.env.example` 补飞书配置说明

**Files:**
- Modify: `.env.example`

**Interfaces:**
- Consumes: 无
- Produces: 文档说明

- [ ] **Step 1: 修改 `.env.example`**

在 Telegram 配置块后新增飞书块：

```dotenv
# ---- 飞书推送通道（可选，复用 hermes 飞书应用机器人）----
# 三个字段必须同时填写，或全部留空（留空则不启用飞书通道）
FEISHU_APP_ID=
FEISHU_APP_SECRET=
# 推送目标：群 chat_id（oc_ 开头）或用户 open_id（ou_ 开头）
FEISHU_CHAT_ID=
```

并把顶部 `WECOM_WEBHOOK_URL` 的注释从"必填"改为"可选，留空则停用企微推送"。

- [ ] **Step 2: 无需测试，检查格式**

Run: `./venv/bin/ruff format --check .env.example` 不适用；目视检查缩进与注释一致性即可。

---

### Task 7: 验证与真实跑通

**Files:**
- 无代码改动；部署相关操作

- [ ] **Step 1: 本地全量验证**

Run: `make test && make lint`
Expected: 全绿

- [ ] **Step 2: 真实跑通前确认凭证来源**

远程 hermes `.env`（`/home/ubuntu/hermes-data/.env`）中读取 `FEISHU_APP_ID` / `FEISHU_APP_SECRET` / `FEISHU_HOME_CHANNEL`，把值填入 Claw_news 远程 `.env` 的 `FEISHU_APP_ID` / `FEISHU_APP_SECRET` / `FEISHU_CHAT_ID`（需要用户授权访问凭证）。

- [ ] **Step 3: 真实推送验证**

部署到远程后触发一次 pipeline，确认交互卡片出现在飞书群。若 `FEISHU_HOME_CHANNEL` 是 open_id 而非 chat_id，调整 `receive_id_type=open_id` 并回归 `test_feishu_pusher.py`。
