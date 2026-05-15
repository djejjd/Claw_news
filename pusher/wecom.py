from datetime import datetime
from typing import Dict, List

import httpx

from collectors.base import HotItem, Category

CATEGORY_LABELS = {
    "ai": "AI 热点",
    "game": "游戏热点",
    "device": "数码硬件",
}

CATEGORY_EMOJI = {
    "ai": "🤖",
    "game": "🎮",
    "device": "📱",
}

SEPARATOR = "━━━━━━━━━━━━━━━━━━━"


def format_message(items: List[HotItem], category: Category) -> str:
    """Format a category's hot list as WeChat Work Markdown message"""
    today = datetime.now().strftime("%m/%d")
    emoji = CATEGORY_EMOJI.get(category, "")
    label = CATEGORY_LABELS.get(category, category)
    lines = [f"{emoji} **{label}** | {today}", SEPARATOR, ""]

    if not items:
        lines.append("> 暂无热点，稍后再来看看")
    else:
        for i, item in enumerate(items, 1):
            title = item.title.replace("\n", " ").strip()
            if item.url:
                lines.append(f"**{i}.** [{title}]({item.url})")
            else:
                lines.append(f"**{i}.** {title}")
            if item.summary:
                summary = item.summary.replace("\n", " ").strip()[:120]
                lines.append(f"> {summary}")
            if i < len(items):
                lines.append("")

    lines.append("")
    lines.append(SEPARATOR)
    return "\n".join(lines)


class WeComPusher:
    """WeChat Work Bot pusher. Sends formatted Markdown messages per category."""

    def __init__(self, webhook_url: str, client: httpx.AsyncClient | None = None):
        self.webhook_url = webhook_url
        self._client = client

    async def push(self, items: Dict[Category, List[HotItem]]) -> None:
        client = self._client or httpx.AsyncClient()
        try:
            for category in ("ai", "game", "device"):
                cat_items = items.get(category, [])
                if not cat_items:
                    continue
                msg = format_message(cat_items, category)
                payload = {"msgtype": "markdown", "markdown": {"content": msg}}
                resp = await client.post(self.webhook_url, json=payload, timeout=15.0)
                resp.raise_for_status()
        finally:
            if self._client is None:
                await client.aclose()
