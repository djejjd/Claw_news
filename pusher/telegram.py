"""Telegram Bot API sender for rendered digest messages."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

_API_BASE_URL = "https://api.telegram.org"


class TelegramError(RuntimeError):
    """A secret-free Telegram delivery failure."""


@dataclass(frozen=True)
class TelegramPushResult:
    messages_sent: int


class TelegramPusher:
    def __init__(self, bot_token: str, chat_id: str, client: httpx.AsyncClient | None = None):
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._client = client

    async def push_messages(self, messages: list[str]) -> TelegramPushResult:
        client = self._client or httpx.AsyncClient()
        sent = 0
        try:
            for message in messages:
                await self._send_message(client, message)
                sent += 1
            return TelegramPushResult(messages_sent=sent)
        finally:
            if self._client is None:
                await client.aclose()

    async def _send_message(self, client: httpx.AsyncClient, text: str) -> None:
        url = f"{_API_BASE_URL}/bot{self._bot_token}/sendMessage"
        try:
            response = await client.post(
                url,
                json={
                    "chat_id": self._chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "link_preview_options": {"is_disabled": True},
                },
                timeout=15.0,
            )
        except httpx.HTTPError as exc:
            raise TelegramError(f"telegram_transport: {type(exc).__name__}") from exc

        body = _response_body(response)
        if response.status_code == 429:
            retry_after = body.get("parameters", {}).get("retry_after") if body else None
            suffix = f" retry_after={retry_after}" if isinstance(retry_after, int) else ""
            raise TelegramError(f"telegram_api: 429{suffix}")
        if response.is_error:
            raise TelegramError(f"telegram_http: {response.status_code}")
        if body is None:
            raise TelegramError("telegram_response: invalid_json")
        if body.get("ok") is not True:
            error_code = body.get("error_code")
            code = error_code if isinstance(error_code, int) else response.status_code
            raise TelegramError(f"telegram_api: {code}")


def _response_body(response: httpx.Response) -> dict | None:
    try:
        body = response.json()
    except ValueError:
        return None
    return body if isinstance(body, dict) else None
