from app.renderers.telegram_html import render_telegram_digest, split_telegram_text
from app.tools.summary_result import SummaryItem, SummaryResult


def _result(*, title="A < B", url="https://example.test/article", summary="Use & enjoy"):
    return SummaryResult(
        headline_items=[
            SummaryItem(
                title=title,
                url=url,
                core_summary=summary,
                importance="高",
                trend="持续关注",
                source="qbitai",
            )
        ],
        daily_judgement="<保持关注>",
    )


def test_renderer_escapes_dynamic_html_text():
    text = "\n".join(render_telegram_digest(_result()))

    assert "A &lt; B" in text
    assert "Use &amp; enjoy" in text
    assert "&lt;保持关注&gt;" in text


def test_renderer_only_uses_http_links_as_href():
    text = "\n".join(render_telegram_digest(_result(url="javascript:alert(1)")))

    assert "href=" not in text
    assert "javascript:" not in text


def test_renderer_adds_safe_http_link():
    text = "\n".join(render_telegram_digest(_result()))

    assert '<a href="https://example.test/article">A &lt; B</a>' in text


def test_split_telegram_text_keeps_each_chunk_within_limit():
    parts = split_telegram_text("first\n" + "x" * 20 + "\nlast", limit=20)

    assert parts == ["first", "x" * 20, "last"]
    assert all(len(part) <= 20 for part in parts)


def test_split_telegram_text_truncates_an_individual_overlong_line():
    parts = split_telegram_text("x" * 21, limit=20)

    assert parts == ["x" * 20]


def test_split_telegram_text_safely_degrades_an_overlong_html_line():
    parts = split_telegram_text("<b>" + "x" * 21 + "</b>", limit=20)

    assert parts == ["x" * 20]
