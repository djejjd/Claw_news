"""Tests for app/tools/llm.py — summarize_news() LLM summarizer."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# ---------------------------------------------------------------------------
# Sample news items
# ---------------------------------------------------------------------------


def _make_news_items(count: int = 3) -> list[dict]:
    """Return a list of sample news dicts matching fetch_news output format."""
    return [
        {
            "title": f"AI打破了{i}项纪录",
            "link": f"https://example.com/news/{i}",
            "summary": f"这是一条关于AI的新闻摘要{i}，内容很长需要LLM总结。",
            "published_at": "2026-05-17",
        }
        for i in range(count)
    ]


# ---------------------------------------------------------------------------
# Normal case helpers
# ---------------------------------------------------------------------------


def _make_valid_response(content: str) -> dict:
    """Build a valid OpenAI-compatible chat completion response JSON."""
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": content,
                }
            }
        ]
    }


def _build_mock_client(
    json_response: dict | None = None,
    *,
    side_effect: Exception | None = None,
) -> AsyncMock:
    """Build a mock httpx.AsyncClient that returns a controlled response.

    Args:
        json_response: The JSON dict to return from response.json().
        side_effect: If set, client.post() raises this exception instead.

    Returns:
        An AsyncMock suitable for use as ``with patch("...", return_value=mock_client)``.
    """
    mock_client = AsyncMock()
    if side_effect is not None:
        mock_client.post.side_effect = side_effect
    else:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = json_response
        mock_response.raise_for_status = lambda: None
        mock_client.post.return_value = mock_response

    mock_client.__aenter__.return_value = mock_client
    return mock_client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSummarizeNews:
    """Tests for summarize_news() — OpenAI-compatible LLM summarizer."""

    # -- Normal path ----------------------------------------------------------

    @pytest.mark.asyncio
    async def test_normal_summary_returns_chinese(self):
        """A valid API response produces a Chinese summary dict."""
        from app.tools.llm import summarize_news

        items = _make_news_items(3)

        import json

        llm_json_output = json.dumps(
            {
                "headline_items": [
                    {
                        "title": "AI打破了0项纪录",
                        "url": "https://example.com/news/0",
                        "core_summary": "测试核心内容",
                        "importance": "高",
                        "trend": "利好",
                    }
                ],
                "daily_judgement": "AI行业持续火热",
            },
            ensure_ascii=False,
        )

        mock_client = _build_mock_client(_make_valid_response(llm_json_output))

        with patch("app.tools.llm.httpx.AsyncClient", return_value=mock_client):
            result = await summarize_news(
                items,
                base_url="https://api.example.com",
                api_key="test-key",
                model="test-model",
            )

        assert isinstance(result, dict)
        assert "headline_items" in result
        assert len(result["headline_items"]) > 0
        assert result["headline_items"][0]["title"] == "AI打破了0项纪录"
        assert result["headline_items"][0]["url"] == "https://example.com/news/0"
        assert result["daily_judgement"] == "AI行业持续火热"

    @pytest.mark.asyncio
    async def test_normal_summary_includes_links(self):
        """The prompt instructs the LLM to keep original links — verify the request body."""
        from app.tools.llm import summarize_news

        items = _make_news_items(2)
        expected_summary = (
            "今日 AI 新闻摘要\n\n1. [新闻](https://example.com/news/0)\n...\n今日一句话判断：还行"
        )

        mock_client = _build_mock_client(_make_valid_response(expected_summary))

        with patch("app.tools.llm.httpx.AsyncClient", return_value=mock_client):
            await summarize_news(
                items,
                base_url="https://api.example.com",
                api_key="test-key",
                model="test-model",
            )

        # Verify the POST was called with correct URL and headers
        call_kwargs = mock_client.post.call_args
        assert call_kwargs is not None
        url = call_kwargs[0][0]
        assert url == "https://api.example.com/chat/completions"

        kwargs = call_kwargs[1]
        assert kwargs["headers"]["Authorization"] == "Bearer test-key"
        assert kwargs["headers"]["Content-Type"] == "application/json"
        assert kwargs["json"]["model"] == "test-model"
        assert kwargs["json"]["temperature"] == 0.7
        messages = kwargs["json"]["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        # The user message must mention every item's link
        user_msg = messages[1]["content"]
        for item in items:
            assert item["link"] in user_msg
        assert kwargs["timeout"] == httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=60.0)

    # -- Empty items ---------------------------------------------------------

    @pytest.mark.asyncio
    async def test_empty_items_returns_fallback(self):
        """When items list is empty, return a deterministic dict without calling API."""
        from app.tools.llm import summarize_news

        mock_client = AsyncMock()
        with patch("app.tools.llm.httpx.AsyncClient", return_value=mock_client):
            result = await summarize_news(
                [],
                base_url="https://api.example.com",
                api_key="test-key",
                model="test-model",
            )

        assert isinstance(result, dict)
        assert result["headline_items"] == []
        assert "暂无" in result["daily_judgement"]
        # Must NOT have called the API
        mock_client.post.assert_not_called()

    # -- HTTP error ----------------------------------------------------------

    @pytest.mark.asyncio
    async def test_http_error_raises_httpx_error(self):
        """When the upstream returns an HTTP error, the exception should propagate."""
        from app.tools.llm import summarize_news

        items = _make_news_items(1)

        error_response = httpx.Response(
            status_code=500,
            request=httpx.Request("POST", "https://api.example.com/chat/completions"),
        )
        mock_client = _build_mock_client(
            side_effect=httpx.HTTPStatusError(
                "Server error",
                request=httpx.Request("POST", "https://api.example.com/chat/completions"),
                response=error_response,
            )
        )

        with patch("app.tools.llm.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(httpx.HTTPStatusError):
                await summarize_news(
                    items,
                    base_url="https://api.example.com",
                    api_key="test-key",
                    model="test-model",
                )

    @pytest.mark.asyncio
    async def test_request_error_propagates(self):
        """Network-level errors (httpx.RequestError) should propagate."""
        from app.tools.llm import summarize_news

        items = _make_news_items(1)

        mock_client = _build_mock_client(side_effect=httpx.RequestError("Connection refused"))

        with patch("app.tools.llm.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(httpx.RequestError):
                await summarize_news(
                    items,
                    base_url="https://api.example.com",
                    api_key="test-key",
                    model="test-model",
                )

    # -- Malformed JSON response ----------------------------------------------

    @pytest.mark.asyncio
    async def test_response_missing_choices(self):
        """A JSON response without the 'choices' key should raise a sensible error."""
        from app.tools.llm import summarize_news

        items = _make_news_items(1)

        mock_client = _build_mock_client({"unexpected": "structure"})

        with patch("app.tools.llm.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises((KeyError, ValueError, RuntimeError, IndexError)):
                await summarize_news(
                    items,
                    base_url="https://api.example.com",
                    api_key="test-key",
                    model="test-model",
                )

    @pytest.mark.asyncio
    async def test_response_empty_choices(self):
        """A response with an empty choices list should raise an error."""
        from app.tools.llm import summarize_news

        items = _make_news_items(1)

        mock_client = _build_mock_client({"choices": []})

        with patch("app.tools.llm.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises((KeyError, ValueError, RuntimeError, IndexError)):
                await summarize_news(
                    items,
                    base_url="https://api.example.com",
                    api_key="test-key",
                    model="test-model",
                )

    @pytest.mark.asyncio
    async def test_response_missing_content(self):
        """A response where choice.message.content is missing should raise an error."""
        from app.tools.llm import summarize_news

        items = _make_news_items(1)

        mock_client = _build_mock_client({"choices": [{"message": {"role": "assistant"}}]})

        with patch("app.tools.llm.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises((KeyError, ValueError, RuntimeError)):
                await summarize_news(
                    items,
                    base_url="https://api.example.com",
                    api_key="test-key",
                    model="test-model",
                )
