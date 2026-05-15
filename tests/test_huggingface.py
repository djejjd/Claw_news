import httpx
import pytest
from collectors.huggingface import HfDailyPapersCollector, HF_API_URL


def test_parse_paper_to_hotitem():
    """Correctly constructs HotItem from API paper dict"""
    collector = HfDailyPapersCollector()
    paper = {
        "title": "Scaling Laws for Multimodal Models",
        "paper": {"id": "abc123"},
        "upvotes": 150,
        "summary": "We study scaling laws across modalities...",
    }
    item = collector._parse_paper(paper)
    assert item.title == "Scaling Laws for Multimodal Models"
    assert item.url == "https://huggingface.co/papers/abc123"
    assert item.category == "ai"
    assert item.source == "huggingface"
    assert 5.0 <= item.source_score <= 10.0
    assert item.pub_date != ""


def test_parse_paper_minimal():
    """Minimal paper data doesn't crash"""
    collector = HfDailyPapersCollector()
    paper = {"title": "Minimal Paper", "paper": {"id": "min1"}}
    item = collector._parse_paper(paper)
    assert item.title == "Minimal Paper"
    assert item.url == "https://huggingface.co/papers/min1"
    assert item.summary == ""


def test_normalize_upvotes_zero():
    """0 votes maps to lowest score"""
    collector = HfDailyPapersCollector()
    score = collector._upvotes_to_score(0, max_votes=200)
    assert score == 0.0


def test_normalize_upvotes_max():
    """Max votes maps to 10"""
    collector = HfDailyPapersCollector()
    score = collector._upvotes_to_score(200, max_votes=200)
    assert score == 10.0


@pytest.mark.asyncio
async def test_collect_returns_list(httpx_mock):
    """Mock API with injected httpx client"""
    mock_papers = [
        {"title": f"Paper {i}", "paper": {"id": f"id{i}"}, "upvotes": 100 - i * 10}
        for i in range(5)
    ]
    httpx_mock.add_response(url=HF_API_URL, json=mock_papers)

    collector = HfDailyPapersCollector(client=httpx.AsyncClient())
    items = await collector.collect()
    assert len(items) == 5
    assert all(item.category == "ai" for item in items)
    assert items[0].source_score >= items[-1].source_score
