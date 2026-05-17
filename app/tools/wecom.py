"""WeCom text message pusher.

Uses the WeCom webhook text message type (msgtype: text) for sending
long-form text content produced by LLM summarization.

Does NOT depend on or import from pusher/wecom.py — this is a standalone,
thin HTTP client for the AI assistant service layer.
"""

from __future__ import annotations

import httpx

# WeCom text messages have an approximate 2048-byte limit in practice.
# We truncate at 2000 characters with an ellipsis indicator to stay
# safely under the limit while retaining a usable message.
MAX_CONTENT_CHARS = 2000
TRUNCATION_INDICATOR = "…"


class WeComError(RuntimeError):
    """Raised when the WeCom webhook returns a business error (errcode != 0)."""

    def __init__(self, errcode: int | None, errmsg: str | None):
        self.errcode = errcode
        self.errmsg = errmsg or "unknown"
        super().__init__(f"errcode={errcode} errmsg={self.errmsg}")


def _truncate(content: str, max_chars: int = MAX_CONTENT_CHARS) -> str:
    """Truncate content to *max_chars* characters, appending an ellipsis."""
    if len(content) <= max_chars:
        return content
    # Keep the first (max_chars - len(indicator)) characters
    keep = max_chars - len(TRUNCATION_INDICATOR)
    return content[:keep] + TRUNCATION_INDICATOR


async def send_text(webhook_url: str, content: str) -> dict:
    """Send a text message to a WeCom webhook.

    Args:
        webhook_url: The full WeCom webhook URL (key included).
        content: The plain-text message content. Oversize content is
                 truncated to ~2000 characters with an ellipsis.

    Returns:
        The parsed JSON response dict, e.g. ``{"errcode": 0, "errmsg": "ok"}``.

    Raises:
        WeComError: When the webhook returns errcode != 0 (business error).
        httpx.HTTPError: On HTTP or network failures (propagated directly).
    """
    truncated = _truncate(content)
    payload = {
        "msgtype": "text",
        "text": {"content": truncated},
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(webhook_url, json=payload, timeout=15.0)
        resp.raise_for_status()

    body = resp.json()
    errcode = body.get("errcode")
    errmsg = body.get("errmsg")

    if errcode is None:
        raise RuntimeError(
            f"WeCom response missing errcode field: {body}"
        )
    if errcode != 0:
        raise WeComError(errcode=errcode, errmsg=errmsg)

    return body
