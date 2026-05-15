import re
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

PERIOD_LABEL = {
    "morning": "早报",
    "evening": "晚报",
}

SEPARATOR = "━━━━━━━━━━━━━━━━━━━"


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def format_message(
    items: List[HotItem],
    category: Category,
    period: str = "morning",
    pushed_urls: set | None = None,
) -> str:
    """格式化某个分类的热点列表为企微 Markdown 消息"""
    if pushed_urls is None:
        pushed_urls = set()

    today = datetime.now().strftime("%m/%d")
    period_label = PERIOD_LABEL.get(period, "")
    emoji = CATEGORY_EMOJI.get(category, "")
    label = CATEGORY_LABELS.get(category, category)
    lines = [f"{emoji} **{label}** | {today} {period_label}", SEPARATOR, ""]

    if not items:
        lines.append("> 暂无热点，稍后再来看看")
    else:
        for i, item in enumerate(items, 1):
            # Build prefix markers
            markers = []
            if item.source == "huggingface":
                markers.append("[EN]")
            if item.url in pushed_urls:
                markers.append("[续]")
            else:
                markers.append("[新]")
            prefix = " ".join(markers)

            title = strip_html(item.title).replace("\n", " ").strip()
            if item.url:
                lines.append(f"**{i}.** {prefix} [{title}]({item.url})")
            else:
                lines.append(f"**{i}.** {prefix} {title}")

            if item.summary:
                summary = strip_html(item.summary).replace("\n", " ").strip()[:120]
                lines.append(f"> {summary}")

            # Source label
            source_label = item.source
            if item.source == "huggingface":
                source_label = "HuggingFace"
            elif item.source == "qbitai":
                source_label = "量子位"
            elif item.source == "yystv":
                source_label = "游研社"
            elif item.source == "ithome":
                source_label = "IT之家"
            elif item.source == "sspai":
                source_label = "少数派"
            elif item.source == "taptap":
                source_label = "TapTap"
            lines.append(f"   — {source_label}")

            if i < len(items):
                lines.append("")

    lines.append("")
    lines.append(SEPARATOR)
    return "\n".join(lines)


class WeComPusher:
    """企微机器人推送器"""

    def __init__(self, webhook_url: str, client: httpx.AsyncClient | None = None):
        self.webhook_url = webhook_url
        self._client = client

    async def push(
        self,
        items: Dict[Category, List[HotItem]],
        period: str = "morning",
        pushed_urls: set | None = None,
    ) -> None:
        if pushed_urls is None:
            pushed_urls = set()

        client = self._client or httpx.AsyncClient()
        try:
            for category in ("ai", "game", "device"):
                cat_items = items.get(category, [])
                if not cat_items:
                    continue
                msg = format_message(cat_items, category, period=period, pushed_urls=pushed_urls)
                payload = {"msgtype": "markdown", "markdown": {"content": msg}}
                resp = await client.post(self.webhook_url, json=payload, timeout=15.0)
                resp.raise_for_status()
        finally:
            if self._client is None:
                await client.aclose()
