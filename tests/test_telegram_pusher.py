import json

import httpx
import pytest

from pusher.telegram import TelegramError, TelegramPusher


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_push_messages_uses_send_message_payload():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

    async with _client(handler) as client:
        result = await TelegramPusher("123:token", "456", client=client).push_messages(
            ["<b>Hi</b>"]
        )

    assert result.messages_sent == 1
    assert str(requests[0].url) == "https://api.telegram.org/bot123:token/sendMessage"
    assert json.loads(requests[0].content) == {
        "chat_id": "456",
        "text": "<b>Hi</b>",
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": True},
    }


@pytest.mark.asyncio
async def test_push_messages_rejects_telegram_api_error_without_secret():
    def handler(request):
        return httpx.Response(200, json={"ok": False, "error_code": 400, "description": "bad chat"})

    async with _client(handler) as client:
        with pytest.raises(TelegramError, match="telegram_api: 400") as exc_info:
            await TelegramPusher("123:token", "456", client=client).push_messages(["hello"])

    assert "123:token" not in str(exc_info.value)
    assert "456" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_push_messages_records_retry_after_for_rate_limit():
    def handler(request):
        return httpx.Response(
            429,
            json={
                "ok": False,
                "error_code": 429,
                "parameters": {"retry_after": 30},
            },
        )

    async with _client(handler) as client:
        with pytest.raises(TelegramError, match="telegram_api: 429 retry_after=30"):
            await TelegramPusher("123:token", "456", client=client).push_messages(["hello"])


@pytest.mark.asyncio
async def test_push_messages_stops_after_the_first_failed_chunk():
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) == 2:
            return httpx.Response(500)
        return httpx.Response(200, json={"ok": True, "result": {}})

    async with _client(handler) as client:
        with pytest.raises(TelegramError, match="telegram_http: 500"):
            await TelegramPusher("123:token", "456", client=client).push_messages(
                ["one", "two", "three"]
            )

    assert len(requests) == 2
