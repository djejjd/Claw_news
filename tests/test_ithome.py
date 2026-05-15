import pytest
from collectors.ithome import ItHomeCollector, ITHOME_RANK_URL


SAMPLE_HTML = """
<html>
<body>
<div class="rank-box">
  <div class="rank-item">
    <a class="title" href="https://www.ithome.com/0/800/001.htm">Apple announces M5 chip</a>
  </div>
  <div class="rank-item">
    <a class="title" href="https://www.ithome.com/0/800/002.htm">Huawei Mate 80 series leaked</a>
  </div>
  <div class="rank-item">
    <a class="title" href="https://www.ithome.com/0/800/003.htm">RTX 5090 benchmark results</a>
  </div>
</div>
</body>
</html>
"""


def test_parse_html_to_items():
    """Extract items from ITHome rank page HTML"""
    collector = ItHomeCollector()
    items = collector._parse_html(SAMPLE_HTML)
    assert len(items) == 3
    assert items[0].title == "Apple announces M5 chip"
    assert items[0].category == "device"
    assert items[0].source == "ithome"
    assert items[0].source_score > items[1].source_score


def test_parse_html_empty():
    """Empty page returns empty list"""
    collector = ItHomeCollector()
    items = collector._parse_html("<html></html>")
    assert items == []


@pytest.mark.asyncio
async def test_collect_mocked(httpx_mock):
    """Mock HTTP response"""
    httpx_mock.add_response(url=ITHOME_RANK_URL, html=SAMPLE_HTML)
    collector = ItHomeCollector()
    items = await collector.collect()
    assert len(items) == 3
    assert all(item.category == "device" for item in items)
