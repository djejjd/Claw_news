"""WeCom text message pusher.

Uses the WeCom webhook text message type (msgtype: text) for sending
long-form text content produced by LLM summarization.

Does NOT depend on or import from pusher/wecom.py — this is a standalone,
thin HTTP client for the AI assistant service layer.
"""

from __future__ import annotations

import httpx

# WeCom text messages have an approximate 2048-byte limit in practice.
# We truncate at 2000 UTF-8 bytes with an ellipsis indicator to stay
# safely under the limit regardless of content character width.
MAX_CONTENT_BYTES = 2000
TRUNCATION_INDICATOR = "…"


class WeComError(RuntimeError):
    """Raised when the WeCom webhook returns a business error (errcode != 0)."""

    def __init__(self, errcode: int | None, errmsg: str | None):
        self.errcode = errcode
        self.errmsg = errmsg or "unknown"
        super().__init__(f"errcode={errcode} errmsg={self.errmsg}")


def _truncate(content: str, max_bytes: int = MAX_CONTENT_BYTES) -> str:
    """Truncate content to fit within *max_bytes* UTF-8 bytes.

    Walks characters one by one, accumulating byte count.  When the
    accumulated size would exceed *max_bytes*, truncation stops.
    Multi-byte characters are never split — the last kept character
    is always fully included.  An ellipsis indicator is appended when
    truncation occurs.
    """
    if not content:
        return content

    content_bytes = content.encode("utf-8")
    if len(content_bytes) <= max_bytes:
        return content

    indicator_bytes = len(TRUNCATION_INDICATOR.encode("utf-8"))
    target_bytes = max_bytes - indicator_bytes
    if target_bytes <= 0:
        return TRUNCATION_INDICATOR

    accumulated = 0
    keep_chars = 0
    for ch in content:
        ch_bytes = len(ch.encode("utf-8"))
        if accumulated + ch_bytes > target_bytes:
            break
        accumulated += ch_bytes
        keep_chars += 1

    return content[:keep_chars] + TRUNCATION_INDICATOR


async def send_text(webhook_url: str, content: str) -> dict:
    """Send a text message to a WeCom webhook.

    Args:
        webhook_url: The full WeCom webhook URL (key included).
        content: The plain-text message content. Oversize content is
                 truncated to fit within ~2000 UTF-8 bytes.

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
