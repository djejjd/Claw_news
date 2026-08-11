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
                headers={"Authorization": f"Bearer {token}"},
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
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "receive_id": self._chat_id,
                        "msg_type": "interactive",
                        "content": content,
                    },
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
