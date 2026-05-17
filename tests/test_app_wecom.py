"""Tests for app/tools/wecom.py — send_text() WeCom text pusher."""

import json

import httpx
import pytest

WEBHOOK = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test-key"


# ---------------------------------------------------------------------------
# Helper to build httpx_mock response expectations inline
# ---------------------------------------------------------------------------

class TestSendTextSuccess:
    """Tests for the happy path: send_text returns the response dict on success."""

    @pytest.mark.asyncio
    async def test_returns_parsed_response(self, httpx_mock):
        """A successful call returns the parsed JSON response dict."""
        from app.tools.wecom import send_text

        httpx_mock.add_response(
            url=WEBHOOK,
            method="POST",
            json={"errcode": 0, "errmsg": "ok"},
        )

        result = await send_text(WEBHOOK, "Hello from test")

        assert result == {"errcode": 0, "errmsg": "ok"}

    @pytest.mark.asyncio
    async def test_posts_text_msgtype(self, httpx_mock):
        """The POST body uses msgtype=text with a text.content field."""
        from app.tools.wecom import send_text

        httpx_mock.add_response(
            url=WEBHOOK,
            method="POST",
            json={"errcode": 0, "errmsg": "ok"},
        )

        await send_text(WEBHOOK, "测试消息")

        request = httpx_mock.get_request()
        payload = json.loads(request.read())
        assert payload["msgtype"] == "text"
        assert "text" in payload
        assert payload["text"]["content"] == "测试消息"


class TestSendTextBusinessError:
    """Tests for WeCom business error handling (errcode != 0)."""

    @pytest.mark.asyncio
    async def test_raises_on_nonzero_errcode(self, httpx_mock):
        """When errcode is not 0, a WeComError exception should be raised."""
        from app.tools.wecom import WeComError, send_text

        httpx_mock.add_response(
            url=WEBHOOK,
            method="POST",
            json={"errcode": 45009, "errmsg": "api freq out of limit"},
        )

        with pytest.raises(WeComError) as exc_info:
            await send_text(WEBHOOK, "rate-limited message")

        assert "45009" in str(exc_info.value)
        assert "api freq out of limit" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_raises_on_unknown_format(self, httpx_mock):
        """When response lacks expected errcode field, treat as error."""
        from app.tools.wecom import send_text

        httpx_mock.add_response(
            url=WEBHOOK,
            method="POST",
            json={"weird": "response"},
        )

        with pytest.raises(RuntimeError):
            await send_text(WEBHOOK, "bad response")


class TestSendTextHttpError:
    """Tests for HTTP-level errors (non-2xx, network issues)."""

    @pytest.mark.asyncio
    async def test_http_500_propagates(self, httpx_mock):
        """HTTP 500 should raise httpx.HTTPStatusError."""
        from app.tools.wecom import send_text

        httpx_mock.add_response(
            url=WEBHOOK,
            method="POST",
            status_code=500,
        )

        with pytest.raises(httpx.HTTPStatusError):
            await send_text(WEBHOOK, "server error")

    @pytest.mark.asyncio
    async def test_timeout_propagates(self, httpx_mock):
        """Connection timeout should raise httpx.TimeoutException."""
        from app.tools.wecom import send_text

        httpx_mock.add_exception(
            httpx.TimeoutException("timed out"),
            url=WEBHOOK,
        )

        with pytest.raises(httpx.TimeoutException):
            await send_text(WEBHOOK, "timeout test")


class TestSendTextOversize:
    """Tests for over-size content handling."""

    @pytest.mark.asyncio
    async def test_truncates_oversize_content(self, httpx_mock):
        """Content exceeding the limit should be truncated with an indicator."""
        from app.tools.wecom import send_text

        httpx_mock.add_response(
            url=WEBHOOK,
            method="POST",
            json={"errcode": 0, "errmsg": "ok"},
        )

        # Create content well above the 2048-byte limit
        long_content = "测" * 3000  # 3000 Chinese characters = way over limit

        await send_text(WEBHOOK, long_content)

        request = httpx_mock.get_request()
        sent_content = json.loads(request.read())["text"]["content"]

        assert len(sent_content) < len(long_content)
        assert "…" in sent_content
        # The truncated version should still start with the original content
        assert sent_content.startswith(long_content[:500])

    @pytest.mark.asyncio
    async def test_short_content_not_truncated(self, httpx_mock):
        """Content under the limit should pass through unchanged."""
        from app.tools.wecom import send_text

        httpx_mock.add_response(
            url=WEBHOOK,
            method="POST",
            json={"errcode": 0, "errmsg": "ok"},
        )

        short_content = "短消息"
        await send_text(WEBHOOK, short_content)

        request = httpx_mock.get_request()
        sent_content = json.loads(request.read())["text"]["content"]
        assert sent_content == short_content
