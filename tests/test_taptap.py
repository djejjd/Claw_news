import pytest
from collectors.taptap import TapTapCollector, TAPTAP_HOT_URL


SAMPLE_HTML = """
<html>
<body>
<div class="tap-top-list">
  <a class="game-card" href="/app/12345">
    <h3>原神</h3>
    <span class="game-genre">角色扮演</span>
  </a>
  <a class="game-card" href="/app/67890">
    <h3>崩坏：星穹铁道</h3>
    <span class="game-genre">回合制</span>
  </a>
  <a class="game-card" href="/app/11111">
    <h3>绝区零</h3>
    <span class="game-genre">动作</span>
  </a>
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
