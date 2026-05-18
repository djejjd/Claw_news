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
