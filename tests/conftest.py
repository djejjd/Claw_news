import pytest
from collectors.base import HotItem


@pytest.fixture
def sample_items():
    """Create cross-category sample data for aggregator tests"""
    import time
    now = time.time()
    return [
        HotItem("AI Paper A", "https://a.com/1", "Summary A", "huggingface", "ai", 9.0, now - 3600),
        HotItem("AI News B", "https://b.com/2", "Summary B", "rss", "ai", 5.0, now - 7200),
        HotItem("AI Old News", "https://b.com/3", "Older AI item", "rss", "ai", 5.0, now - 100000),
        HotItem("Game News C", "https://c.com/3", "Summary C", "taptap", "game", 8.0, now - 1800),
        HotItem("Game News D", "https://d.com/4", "Summary D", "rss", "game", 5.0, now - 40000),
        HotItem("Game Old News", "https://d.com/5", "Very old game item", "rss", "game", 5.0, now - 200000),
        HotItem("Device E", "https://e.com/5", "Summary E", "ithome", "device", 7.0, now - 600),
        HotItem("Device F", "https://f.com/6", "Summary F", "rss", "device", 5.0, now - 50000),
        # Duplicate URL - should be deduped
        HotItem("AI Paper A dup", "https://a.com/1", "Dup", "rss", "ai", 3.0, now - 3600),
    ]
