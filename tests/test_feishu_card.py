"""render_feishu_card 单元测试。"""

from app.renderers.feishu_card import render_feishu_card
from app.tools.summary_result import SummaryItem, SummaryResult


def make_item(
    title="GPT-5 发布",
    url="https://example.com/gpt5",
    core_summary="OpenAI 推出新一代模型。",
    importance="高",
    trend="上升",
    source="qbitai",
    display_category="AI",
    topic_label=None,
):
    return SummaryItem(
        title=title,
        url=url,
        core_summary=core_summary,
        importance=importance,
        trend=trend,
        source=source,
        display_category=display_category,
        topic_label=topic_label,
    )


def make_result(items=None, daily_judgement="今天 AI 领域动作频频。"):
    return SummaryResult(headline_items=items or [], daily_judgement=daily_judgement)


def test_header_present():
    card = render_feishu_card(make_result([make_item()]))
    assert card["header"]["title"]["content"] == "AI / 游戏 / 工具 热点"
    assert card["config"]["wide_screen_mode"] is True


def test_element_contains_title_and_link():
    card = render_feishu_card(make_result([make_item(title="GPT-5 发布", url="https://x.com/1")]))
    text = "".join(e["text"]["content"] for e in card["elements"] if e["tag"] == "div")
    assert "GPT-5 发布" in text
    assert "https://x.com/1" in text


def test_contains_core_summary_and_source():
    card = render_feishu_card(make_result([make_item(core_summary="OpenAI 发布模型。")]))
    text = "".join(e["text"]["content"] for e in card["elements"] if e["tag"] == "div")
    assert "OpenAI 发布模型。" in text
    assert "量子位" in text  # qbitai → 量子位 · 国内


def test_daily_judgement_in_note():
    card = render_feishu_card(make_result([make_item()], daily_judgement="AI 行业波澜不惊。"))
    notes = [e for e in card["elements"] if e["tag"] == "note"]
    assert any("AI 行业波澜不惊" in json_str(n) for n in notes)


def test_title_markdown_escaped():
    """标题中的 * 和 [ 必须转义，防止破坏 lark_md。"""
    card = render_feishu_card(make_result([make_item(title="真*标题[测试]")]))
    text = "".join(e["text"]["content"] for e in card["elements"] if e["tag"] == "div")
    assert "真\\*标题\\[测试\\]" in text


def test_no_items_still_has_header_and_judgement():
    card = render_feishu_card(make_result([], daily_judgement="今日无内容。"))
    assert card["header"]["title"]["content"] == "AI / 游戏 / 工具 热点"
    assert any("今日无内容" in json_str(n) for n in card["elements"] if n["tag"] == "note")


def test_github_items_rendered():
    """github_items 渲染为"今日值得看项目"段。"""
    from types import SimpleNamespace

    gh = SimpleNamespace(
        full_name="anthropics/claude-code",
        url="https://x.com/r",
        stars=5000,
        language="Python",
        description="AI 工具",
    )
    card = render_feishu_card(
        make_result([make_item()]),
        github_items=[gh],
        github_recommendations={"anthropics/claude-code": "值得关注"},
    )
    text = "".join(e["text"]["content"] for e in card["elements"] if e["tag"] == "div")
    assert "anthropics/claude-code" in text
    assert "值得关注" in text


def test_item_numbering_is_sequential_per_category():
    """同一分类内条目编号连续（1,2），不跳号。"""
    items = [
        make_item(title="AI-1", core_summary="第一条", display_category="AI"),
        make_item(title="AI-2", core_summary="第二条", display_category="AI"),
        make_item(title="工具-1", core_summary="第三条", display_category="工具"),
        make_item(title="工具-2", core_summary="第四条", display_category="工具"),
    ]
    card = render_feishu_card(make_result(items))
    text = "".join(e["text"]["content"] for e in card["elements"] if e["tag"] == "div")
    assert "**1.**" in text
    assert "**2.**" in text
    assert "**3.**" not in text


def json_str(element):
    import json

    return json.dumps(element, ensure_ascii=False)
