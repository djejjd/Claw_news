from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

import httpx

from collectors.base import Category, HotItem, normalize_category

CATEGORY_LABELS = {
    "ai": "AI 热点",
    "game": "游戏热点",
    "tool": "数码硬件",
}

CATEGORY_EMOJI = {
    "ai": "🤖",
    "game": "🎮",
    "tool": "📱",
}

PERIOD_LABEL = {
    "morning": "早报",
    "evening": "晚报",
}

SEPARATOR = "━━━━━━━━━━━━━━━━━━━"


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def format_message(
    items: list[HotItem],
    category: Category,
    period: str = "morning",
    pushed_urls: set[str] | None = None,
) -> str:
    """格式化某个分类的热点列表为企微 Markdown 消息"""
    if pushed_urls is None:
        pushed_urls = set()

    display_category = normalize_category(category)
    today = datetime.now().strftime("%m/%d")
    period_label = PERIOD_LABEL.get(period, "")
    emoji = CATEGORY_EMOJI.get(display_category, "")
    label = CATEGORY_LABELS.get(display_category, display_category)
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

            # Source label + region
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

            region = "国外" if item.source == "huggingface" else "国内"
            lines.append(f"   — {source_label} · {region}")

            if i < len(items):
                lines.append("")

    lines.append("")
    lines.append(SEPARATOR)
    return "\n".join(lines)


@dataclass
class PushResult:
    category: str
    success: bool
    urls: list[str]
    errcode: int | None = None
    errmsg: str | None = None


class WeComError(RuntimeError):
    def __init__(self, category: str, errcode: int | None, errmsg: str | None):
        self.category = category
        self.errcode = errcode
        self.errmsg = errmsg or "unknown"
        super().__init__(f"category={category} errcode={errcode} errmsg={self.errmsg}")


class WeComPusher:
    """企微机器人推送器"""

    def __init__(self, webhook_url: str, client: httpx.AsyncClient | None = None):
        self.webhook_url = webhook_url
        self._client = client

    async def push_category(
        self,
        category: Category,
        items: list[HotItem],
        period: str = "morning",
        pushed_urls: set[str] | None = None,
    ) -> PushResult:
        if pushed_urls is None:
            pushed_urls = set()

        normalized_category = normalize_category(category)
        msg = format_message(items, normalized_category, period=period, pushed_urls=pushed_urls)
        payload = {"msgtype": "markdown", "markdown": {"content": msg}}
        urls = [item.url for item in items if item.url]

        client = self._client or httpx.AsyncClient()
        try:
            resp = await client.post(self.webhook_url, json=payload, timeout=15.0)
            resp.raise_for_status()
            body = resp.json()
            if body.get("errcode") != 0:
                raise WeComError(
                    category=normalized_category,
                    errcode=body.get("errcode"),
                    errmsg=body.get("errmsg"),
                )
            return PushResult(
                category=normalized_category,
                success=True,
                urls=urls,
                errcode=0,
                errmsg=body.get("errmsg"),
            )
        finally:
            if self._client is None:
                await client.aclose()

    async def push_single_markdown(self, content: str) -> PushResult:
        """推送单条 markdown 消息，不复用逐 category 多消息语义"""
        payload = {"msgtype": "markdown", "markdown": {"content": content}}

        client = self._client or httpx.AsyncClient()
        try:
            resp = await client.post(self.webhook_url, json=payload, timeout=15.0)
            resp.raise_for_status()
            body = resp.json()
            if body.get("errcode") != 0:
                raise WeComError(
                    category="ai_digest",
                    errcode=body.get("errcode"),
                    errmsg=body.get("errmsg"),
                )
            return PushResult(
                category="ai_digest",
                success=True,
                urls=[],
                errcode=0,
                errmsg=body.get("errmsg"),
            )
        finally:
            if self._client is None:
                await client.aclose()

    async def push(self, items_by_category, period="morning", pushed_urls=None):
        results = []
        normalized_items = {
            "ai": list(items_by_category.get("ai", [])),
            "tool": [
                *items_by_category.get("tool", []),
                *items_by_category.get("device", []),
            ],
            "game": list(items_by_category.get("game", [])),
        }

        for category in ("ai", "tool", "game"):
            cat_items = normalized_items[category]
            if not cat_items:
                continue
            result = await self.push_category(
                category=category,
                items=cat_items,
                period=period,
                pushed_urls=pushed_urls,
            )
            results.append(result)
        return results
