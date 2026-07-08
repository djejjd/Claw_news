"""WeCom markdown renderer for structured AI news digests.

Consumes a SummaryResult and produces a single WeCom-compatible markdown
message string suitable for the ``msgtype: markdown`` webhook endpoint.
"""

from __future__ import annotations

import re
from collections import OrderedDict

from app.tools.summary_result import SummaryResult

MAX_PREVIEW_CHARS = 200
MAX_DIGEST_ITEMS = 10
DISPLAY_CATEGORY_ORDER = ("AI", "工具", "游戏")

# Characters that have special meaning in WeCom markdown and may appear
# inside article titles.  Escaping them prevents accidental formatting
# or broken link syntax.
_MARKDOWN_SPECIAL = re.compile(r"([*_`\[\]\\])")


def _escape_title(text: str) -> str:
    """Escape markdown meta-characters inside a title string."""
    return _MARKDOWN_SPECIAL.sub(r"\\\1", text)


def render_digest(result: SummaryResult, github_items: list | None = None) -> str:
    """Consume *result* and produce a single WeCom markdown string.

    The output follows the project's WeCom markdown convention:

    - A level-1 heading serves as the message title.
    - Each headline item becomes a numbered entry with a markdown link title.
    - Core summary, importance and trend are presented as block-quoted lines.
    - The daily one-sentence judgement is appended at the bottom as a
      block-quote.
    """
    lines = ["# AI / 游戏 / 工具 热点", ""]

    items = (result.headline_items or [])[:MAX_DIGEST_ITEMS]
    grouped_items: OrderedDict[str, list] = OrderedDict(
        (category, []) for category in DISPLAY_CATEGORY_ORDER
    )
    for item in items:
        category = item.display_category if item.display_category in grouped_items else "AI"
        grouped_items[category].append(item)

    item_number = 1
    rendered_item_count = 0
    for category, category_items in grouped_items.items():
        if not category_items:
            continue

        lines.append(f"【{category}】{len(category_items)}")
        for item in category_items:
            safe_title = _escape_title(item.title)
            url = item.url or ""
            topic_label = f"[{item.topic_label}] " if item.topic_label else ""

            if url:
                lines.append(f"**{item_number}.** {topic_label}[{safe_title}]({url})")
            else:
                lines.append(f"**{item_number}.** {topic_label}{safe_title}")

            source_part = f" — {item.source}" if item.source else ""
            lines.append(f"> {item.core_summary} | 重要性：{item.importance} | 趋势：{item.trend}{source_part}")

            item_number += 1
            rendered_item_count += 1

            if rendered_item_count < len(items):
                lines.append("")

    if result.daily_judgement:
        lines.append("")
        lines.append(f"> 今日一句话判断：{result.daily_judgement}")

    if github_items:
        lines.append("")
        lines.append("## 今日值得看项目")
        lines.append("")
        for i, item in enumerate(github_items[:3], 1):
            language = f" · {item.language}" if item.language else ""
            description = item.description or "暂无简介"
            lines.append(f"**{i}.** [{item.full_name}]({item.url})")
            lines.append(f"> {description}")
            lines.append(f"> ⭐ {item.stars}{language}")
            if i < min(len(github_items), 3):
                lines.append("")

    return "\n".join(lines)


def make_preview(markdown: str, max_chars: int = MAX_PREVIEW_CHARS) -> str:
    """Return the first *max_chars* characters of *markdown* as a preview."""
    return markdown[:max_chars]
