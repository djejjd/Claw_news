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

        def _handler(request, _url=url_partial, _status=status, _body=body):
            if _url not in str(request.url):
                return httpx.Response(500, json={"code": -1, "msg": "unexpected url"})
            return httpx.Response(_status, json=_body)

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
    client = _client(
        [
            ("POST", "/auth/v3/tenant_access_token/internal", 200, token_resp),
            ("POST", "/im/v1/messages", 200, msg_resp),
        ]
    )
    pusher = FeishuPusher(_APP_ID, _APP_SECRET, _CHAT_ID, client=client)
    result = await pusher.push_card({"config": {}, "elements": []})
    assert result.messages_sent == 1


async def test_push_card_requests_token_with_credentials():
    captured = {}

    def _handler(request):
        if "/auth/v3/tenant_access_token" in str(request.url):
            captured["body"] = json.loads(request.content)
            captured["url"] = str(request.url)
            return httpx.Response(
                200, json={"code": 0, "tenant_access_token": "t-abc", "expire": 7200}
            )
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
            return httpx.Response(
                200, json={"code": 0, "tenant_access_token": "t-abc", "expire": 7200}
            )
        captured["body"] = json.loads(request.content)
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json={"code": 0})

    client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
    card = {"config": {"wide_screen_mode": True}, "elements": [{"tag": "div"}]}
    pusher = FeishuPusher(_APP_ID, _APP_SECRET, _CHAT_ID, client=client)
    await pusher.push_card(card)
    assert "receive_id_type=chat_id" in captured["url"]
    assert captured["body"]["receive_id"] == _CHAT_ID
    assert captured["body"]["msg_type"] == "interactive"
    assert json.loads(captured["body"]["content"]) == card
    assert captured["auth"] == "Bearer t-abc"


async def test_push_card_invalid_token_retries_once():
    """code==99991663（token 无效）时重取 token 后重试一次。"""
    calls = []
    auth_headers = []

    def _handler(request):
        if "/auth/v3/tenant_access_token" in str(request.url):
            calls.append("token")
            return httpx.Response(
                200, json={"code": 0, "tenant_access_token": "t-abc", "expire": 7200}
            )
        calls.append("msg")
        auth_headers.append(request.headers.get("Authorization"))
        if calls.count("msg") == 1:
            return httpx.Response(200, json={"code": 99991663, "msg": "token invalid"})
        return httpx.Response(200, json={"code": 0})

    client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
    pusher = FeishuPusher(_APP_ID, _APP_SECRET, _CHAT_ID, client=client)
    result = await pusher.push_card({"config": {}, "elements": []})
    assert result.messages_sent == 1
    assert calls.count("token") == 2
    assert auth_headers == ["Bearer t-abc", "Bearer t-abc"]


async def test_push_card_api_error_raises():
    client = _client(
        [
            (
                "POST",
                "/auth/v3/tenant_access_token/internal",
                200,
                {"code": 0, "tenant_access_token": "t", "expire": 7200},
            ),
            ("POST", "/im/v1/messages", 200, {"code": 99991400, "msg": "bad request"}),
        ]
    )
    pusher = FeishuPusher(_APP_ID, _APP_SECRET, _CHAT_ID, client=client)
    with pytest.raises(FeishuError, match="99991400"):
        await pusher.push_card({"config": {}, "elements": []})


async def test_push_card_http_error_raises():
    client = _client(
        [
            (
                "POST",
                "/auth/v3/tenant_access_token/internal",
                200,
                {"code": 0, "tenant_access_token": "t", "expire": 7200},
            ),
            ("POST", "/im/v1/messages", 500, {"code": -1}),
        ]
    )
    pusher = FeishuPusher(_APP_ID, _APP_SECRET, _CHAT_ID, client=client)
    with pytest.raises(FeishuError, match="feishu_http"):
        await pusher.push_card({"config": {}, "elements": []})


async def test_error_message_contains_no_secret():
    """FeishuError 消息不得包含 app_secret 或 token。"""
    client = _client(
        [
            (
                "POST",
                "/auth/v3/tenant_access_token/internal",
                200,
                {"code": 0, "tenant_access_token": "t", "expire": 7200},
            ),
            ("POST", "/im/v1/messages", 200, {"code": 99991400, "msg": "bad"}),
        ]
    )
    pusher = FeishuPusher(_APP_ID, _APP_SECRET, _CHAT_ID, client=client)
    with pytest.raises(FeishuError) as exc_info:
        await pusher.push_card({"config": {}, "elements": []})
    assert _APP_SECRET not in str(exc_info.value)
    assert "t-abc" not in str(exc_info.value)
