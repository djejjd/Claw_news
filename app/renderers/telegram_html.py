"""Telegram HTML renderer for structured news digests."""

from __future__ import annotations

import re
from html import escape
from urllib.parse import urlparse

from app.tools.summary_result import SummaryResult

MAX_TELEGRAM_MESSAGE_CHARS = 4096
_HTML_TAG = re.compile(r"<[^>]*>")
_SOURCE_LABEL = {
    "qbitai": "量子位",
    "leiphone": "雷锋网",
    "jiqizhixin": "机器之心",
    "meituan_tech": "美团技术",
    "openai_blog": "OpenAI",
    "sspai": "少数派",
    "ithome": "IT之家",
    "appinn": "小众软件",
    "cloudflare_cn": "Cloudflare",
    "yystv": "游研社",
    "gcores": "机核",
    "chuapp": "触乐",
    "indienova": "indienova",
    "eurogamer": "Eurogamer",
    "huggingface": "HuggingFace",
    "github": "GitHub",
    "taptap": "TapTap",
}
_OVERSEAS_SOURCES = frozenset({"openai_blog", "huggingface", "deepmind", "eurogamer"})


def _safe_link(title: str, url: str) -> str:
    parsed = urlparse(url)
    safe_title = escape(title, quote=True)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return f'<a href="{escape(url, quote=True)}">{safe_title}</a>'
    return safe_title


def _source_display(source: str) -> str:
    label = _SOURCE_LABEL.get(source, source)
    region = "国外" if source in _OVERSEAS_SOURCES else "国内"
    return f"{label} · {region}"


def split_telegram_text(text: str, limit: int = MAX_TELEGRAM_MESSAGE_CHARS) -> list[str]:
    """Split text at line boundaries, truncating a line that exceeds Telegram's limit."""
    if limit <= 0:
        raise ValueError("limit must be positive")

    chunks: list[str] = []
    current = ""
    for line in text.splitlines():
        if not line:
            continue
        if len(line) > limit:
            line = _HTML_TAG.sub("", line)[:limit]
        candidate = line if not current else f"{current}\n{line}"
        if current and len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def render_telegram_digest(
    result: SummaryResult,
    github_items: list | None = None,
    pushed_urls: set[str] | None = None,
    github_recommendations: dict[str, str] | None = None,
) -> list[str]:
    """Render a digest as safe Telegram HTML message chunks."""
    lines = ["<b>AI / 游戏 / 工具 热点</b>"]
    for number, item in enumerate((result.headline_items or [])[:10], 1):
        marker = "续" if pushed_urls is not None and item.url in pushed_urls else "新"
        topic = f"[{escape(item.topic_label, quote=True)}] " if item.topic_label else ""
        lines.append(f"<b>{number}.</b> {topic}[{marker}] {_safe_link(item.title, item.url or '')}")
        source = _source_display(item.source) if item.source else ""
        lines.append(
            f"{escape(item.core_summary, quote=True)} | "
            f"重要性：{escape(item.importance, quote=True)} | "
            f"趋势：{escape(item.trend, quote=True)} — {escape(source, quote=True)}"
        )

    if result.daily_judgement:
        lines.append(f"<b>今日一句话判断：</b>{escape(result.daily_judgement, quote=True)}")

    if github_items:
        lines.append("<b>今日值得看项目</b>")
        for number, item in enumerate(github_items[:3], 1):
            reason = (github_recommendations or {}).get(item.full_name, "")
            lines.append(f"<b>{number}.</b> {_safe_link(item.full_name, item.url or '')}")
            lines.append(escape(item.description or "暂无简介", quote=True))
            details = f"⭐ {item.stars}" + (f" · {item.language}" if item.language else "")
            if reason:
                details += f" | 💡 {escape(reason, quote=True)}"
            lines.append(details)

    return split_telegram_text("\n".join(lines))
