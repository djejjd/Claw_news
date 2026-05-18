"""WeCom markdown renderer for structured AI news digests.

Consumes a SummaryResult and produces a single WeCom-compatible markdown
message string suitable for the ``msgtype: markdown`` webhook endpoint.
"""

from __future__ import annotations

import re

from app.tools.summary_result import SummaryResult

MAX_PREVIEW_CHARS = 200

# Characters that have special meaning in WeCom markdown and may appear
# inside article titles.  Escaping them prevents accidental formatting
# or broken link syntax.
_MARKDOWN_SPECIAL = re.compile(r"([*_`\[\]\\])")


def _escape_title(text: str) -> str:
    """Escape markdown meta-characters inside a title string."""
    return _MARKDOWN_SPECIAL.sub(r"\\\1", text)


def render_digest(result: SummaryResult) -> str:
    """Consume *result* and produce a single WeCom markdown string.

    The output follows the project's WeCom markdown convention:

    - A level-1 heading serves as the message title.
    - Each headline item becomes a numbered entry with a markdown link title.
    - Core summary, importance and trend are presented as block-quoted lines.
    - The daily one-sentence judgement is appended at the bottom as a
      block-quote.
    """
    lines = ["# 今日 AI 新闻摘要", ""]

    items = result.headline_items or []
    for i, item in enumerate(items, 1):
        safe_title = _escape_title(item.title)
        url = item.url or ""

        if url:
            lines.append(f"**{i}.** [{safe_title}]({url})")
        else:
            lines.append(f"**{i}.** {safe_title}")

        lines.append(f"> 核心内容：{item.core_summary}")
        lines.append(f">")
        lines.append(f"> 重要性：{item.importance}")
        lines.append(f">")
        lines.append(f"> 趋势判断：{item.trend}")

        if i < len(items):
            lines.append("")

    if result.daily_judgement:
        lines.append("")
        lines.append(f"> 今日一句话判断：{result.daily_judgement}")

    return "\n".join(lines)


def make_preview(markdown: str, max_chars: int = MAX_PREVIEW_CHARS) -> str:
    """Return the first *max_chars* characters of *markdown* as a preview."""
    return markdown[:max_chars]
