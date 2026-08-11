"""飞书交互卡片渲染器 — 把日报 SummaryResult 映射为飞书 interactive 卡片。

复用 wecom_markdown 的转义与来源标签逻辑，避免重复。
"""

from __future__ import annotations

from collections import OrderedDict

from app.renderers.wecom_markdown import (
    DISPLAY_CATEGORY_ORDER,
    MAX_DIGEST_ITEMS,
    _escape_title,
    _source_display,
)
from app.tools.summary_result import SummaryResult

_CARD_TITLE = "AI / 游戏 / 工具 热点"


def render_feishu_card(
    result: SummaryResult,
    github_items: list | None = None,
    pushed_urls: set[str] | None = None,
    github_recommendations: dict[str, str] | None = None,
) -> dict:
    """把 *result* 渲染为飞书 interactive 卡片 dict。"""
    elements: list[dict] = []
    items = (result.headline_items or [])[:MAX_DIGEST_ITEMS]
    grouped_items: OrderedDict[str, list] = OrderedDict(
        (category, []) for category in DISPLAY_CATEGORY_ORDER
    )
    for item in items:
        category = item.display_category if item.display_category in grouped_items else "AI"
        grouped_items[category].append(item)

    for category, category_items in grouped_items.items():
        if not category_items:
            continue
        lines = [f"**【{category}】{len(category_items)}**"]
        item_number = 1
        for item in category_items:
            safe_title = _escape_title(item.title)
            url = item.url or ""
            topic_label = f"[{item.topic_label}] " if item.topic_label else ""
            is_new = "新" if pushed_urls is None or url not in pushed_urls else "续"
            marker = f"[{is_new}] "
            number = item_number
            if url:
                lines.append(f"**{number}.** {topic_label}{marker}[{safe_title}]({url})")
            else:
                lines.append(f"**{number}.** {topic_label}{marker}{safe_title}")
            source_display = _source_display(item.source) if item.source else ""
            lines.append(
                f"> {item.core_summary} | 重要性：{item.importance} | "
                f"趋势：{item.trend} — {source_display}"
            )
            item_number += 1
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}})
        elements.append({"tag": "hr"})

    if github_items:
        lines = ["**今日值得看项目**"]
        for i, item in enumerate(github_items[:3], 1):
            language = f" · {item.language}" if item.language else ""
            description = item.description or "暂无简介"
            reason = (github_recommendations or {}).get(item.full_name, "")
            reason_line = f" | 💡 {reason}" if reason else ""
            lines.append(f"**{i}.** [{item.full_name}]({item.url})")
            lines.append(f"> {description}")
            lines.append(f"> ⭐ {item.stars}{language}{reason_line}")
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}})
        elements.append({"tag": "hr"})

    # 去掉最后一个多余分隔线
    if elements and elements[-1]["tag"] == "hr":
        elements.pop()

    if result.daily_judgement:
        elements.append(
            {
                "tag": "note",
                "elements": [
                    {"tag": "plain_text", "content": f"今日一句话判断：{result.daily_judgement}"}
                ],
            }
        )

    return {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "content": _CARD_TITLE}, "template": "blue"},
        "elements": elements,
    }
