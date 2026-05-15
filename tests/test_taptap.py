import pytest
from collectors.taptap import TapTapCollector, TAPTAP_HOT_URL


SAMPLE_HTML = """
<html>
<body>
<div class="game-list-cell tap-router rank-game-cell">
  <a href="/app/12345"><span>App icon</span></a>
  <span class="game-list-cell-title">原神</span>
</div>
<div class="game-list-cell tap-router rank-game-cell">
  <a href="/app/67890"><span>App icon</span></a>
  <span class="game-list-cell-title">崩坏：星穹铁道</span>
</div>
<div class="game-list-cell tap-router rank-game-cell">
  <a href="/app/11111"><span>App icon</span></a>
  <span class="game-list-cell-title">绝区零</span>
</div>
</body>
</html>
"""


def test_parse_html_to_items():
    """Extract game list from TapTap hot page HTML"""
    collector = TapTapCollector()
    items = collector._parse_html(SAMPLE_HTML)
    assert len(items) == 3
    assert items[0].title == "原神"
    assert items[0].url == "https://www.taptap.cn/app/12345"
    assert items[0].category == "game"
    assert items[0].source == "taptap"
    assert items[0].source_score > items[1].source_score  # rank 1 > rank 2
    assert all(item.pub_date != "" for item in items)


def test_parse_html_empty():
    """Empty page returns empty list"""
    collector = TapTapCollector()
    items = collector._parse_html("<html></html>")
    assert items == []


@pytest.mark.asyncio
async def test_collect_mocked(httpx_mock):
    """Mock HTTP response, verify full collect flow"""
    httpx_mock.add_response(url=TAPTAP_HOT_URL, html=SAMPLE_HTML)
    collector = TapTapCollector()
    items = await collector.collect()
    assert len(items) == 3
    assert all(item.category == "game" for item in items)
