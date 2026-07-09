from unittest.mock import AsyncMock, patch

import httpx
import pytest

from collectors.github import GitHubCollector


@pytest.mark.asyncio
async def test_collect_queries_multiple_queries_and_deduplicates():
    """多查询召回，按 full_name 去重"""
    payloads = [
        {"items": [{"full_name": "owner/a", "html_url": "https://github.com/owner/a",
                     "description": "a", "stargazers_count": 100, "language": "Python",
                     "created_at": "2025-01-01T00:00:00Z",
                     "updated_at": "2026-07-08T00:00:00Z",
                     "pushed_at": "2026-07-08T00:00:00Z"}]},
        {"items": [{"full_name": "owner/a", "html_url": "https://github.com/owner/a",
                     "description": "a", "stargazers_count": 100, "language": "Python",
                     "created_at": "2025-01-01T00:00:00Z",
                     "updated_at": "2026-07-08T00:00:00Z",
                     "pushed_at": "2026-07-08T00:00:00Z"}]},
    ] * 4  # repeat for all 8 queries
    responses = []
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

    assert len(items) == 1  # deduped
    assert items[0].full_name == "owner/a"


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
async def test_collect_preserves_extra_fields():
    """验证创建日期、更新日期等新字段被保留"""
    payload = {
        "items": [{
            "full_name": "owner/repo",
            "html_url": "https://github.com/owner/repo",
            "description": "test",
            "stargazers_count": 500,
            "forks_count": 50,
            "watchers_count": 30,
            "language": "Rust",
            "created_at": "2024-06-01T00:00:00Z",
            "updated_at": "2026-07-08T00:00:00Z",
            "pushed_at": "2026-07-08T00:00:00Z",
            "topics": ["llm"],
        }]
    }
    response = AsyncMock()
    response.raise_for_status = lambda: None
    response.json = lambda: payload

    with patch("collectors.github.httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client.get.return_value = response
        client_cls.return_value.__aenter__.return_value = client
        items = await GitHubCollector().collect()

    assert len(items) == 1
    item = items[0]
    assert item.stars == 500
    assert item.forks == 50
    assert item.watchers == 30
    assert item.created_at == "2024-06-01T00:00:00Z"
    assert item.pushed_at == "2026-07-08T00:00:00Z"
    assert "llm" in item.matched_topics


@pytest.mark.asyncio
async def test_collect_returns_partial_results_on_partial_failures():
    success_payload = {
        "items": [{
            "full_name": "owner/a",
            "html_url": "https://github.com/owner/a",
            "description": "a",
            "stargazers_count": 100,
            "language": "Python",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2026-07-08T00:00:00Z",
            "pushed_at": "2026-07-08T00:00:00Z",
        }]
    }
    ok_response = AsyncMock()
    ok_response.raise_for_status = lambda: None
    ok_response.json = lambda: success_payload

    error_request = httpx.Request("GET", "https://api.github.com/search/repositories")
    error_response = httpx.Response(504, request=error_request)
    persistent_error = httpx.HTTPStatusError(
        "Server error '504 Gateway Timeout'", request=error_request, response=error_response,
    )

    with patch("collectors.github.httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        # 8 queries: first 2 succeed, rest 6 fail
        client.get.side_effect = [ok_response, ok_response] + [persistent_error] * 18
        client_cls.return_value.__aenter__.return_value = client

        items = await GitHubCollector().collect()

    assert len(items) >= 1
    assert items[0].full_name == "owner/a"
