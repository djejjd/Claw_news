from unittest.mock import AsyncMock, patch

import pytest

from collectors.github import GitHubCollector


@pytest.mark.asyncio
async def test_collect_parses_and_caps_three_repos():
    payload = {
        "items": [
            {
                "full_name": f"owner/repo{i}",
                "html_url": f"https://github.com/owner/repo{i}",
                "description": f"repo {i}",
                "stargazers_count": 100 - i,
                "language": "Python",
            }
            for i in range(5)
        ]
    }
    response = AsyncMock()
    response.raise_for_status = lambda: None
    response.json = lambda: payload

    with patch("collectors.github.httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client.get.return_value = response
        client_cls.return_value.__aenter__.return_value = client
        items = await GitHubCollector().collect()

    assert len(items) == 3
    assert items[0].full_name == "owner/repo0"
    assert items[0].stars == 100


@pytest.mark.asyncio
async def test_collect_empty_result_returns_empty_list():
    response = AsyncMock()
    response.raise_for_status = lambda: None
    response.json = lambda: {"items": []}

    with patch("collectors.github.httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client.get.return_value = response
        client_cls.return_value.__aenter__.return_value = client
        items = await GitHubCollector().collect()

    assert items == []


@pytest.mark.asyncio
async def test_collect_queries_each_topic_and_merges_unique_repos():
    responses = []
    payloads = [
        {"items": [
            {"full_name": "owner/a", "html_url": "https://github.com/owner/a", "description": "a", "stargazers_count": 100, "language": "Python"},
            {"full_name": "owner/shared", "html_url": "https://github.com/owner/shared", "description": "shared", "stargazers_count": 90, "language": "Python"},
        ]},
        {"items": [
            {"full_name": "owner/b", "html_url": "https://github.com/owner/b", "description": "b", "stargazers_count": 95, "language": "TypeScript"},
        ]},
        {"items": [
            {"full_name": "owner/shared", "html_url": "https://github.com/owner/shared", "description": "shared", "stargazers_count": 90, "language": "Python"},
        ]},
    ]
    for payload in payloads:
        response = AsyncMock()
        response.raise_for_status = lambda: None
        response.json = lambda payload=payload: payload
        responses.append(response)

    with patch("collectors.github.httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client.get.side_effect = responses
        client_cls.return_value.__aenter__.return_value = client
        items = await GitHubCollector().collect()

    assert [item.full_name for item in items] == ["owner/a", "owner/b", "owner/shared"]
    assert client.get.await_count == 3
