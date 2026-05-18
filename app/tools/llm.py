"""OpenAI-compatible LLM client for news summarization.

Uses raw httpx calls — no vendor-specific SDK required.
"""

from __future__ import annotations

import json
import logging

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
你是一个专业的AI新闻分析师。请根据提供的新闻列表，生成一份中文的《今日 AI 新闻摘要》。

输出格式要求：
- 标题为「今日 AI 新闻摘要」
- 每条新闻必须包含：
  - 标题（使用 Markdown 链接格式：[标题](原文链接)）
  - 核心内容：该新闻的核心内容，1-2 句话
  - 重要性：该新闻对AI行业的重要性判断（高/中/低）
  - 趋势判断：该新闻反映的行业趋势
- 文末包含「今日一句话判断」，用一句话总结今天的AI新闻整体态势
- 必须使用中文输出
- 每条新闻的标题必须保留原文链接"""

_USER_PROMPT_TEMPLATE = """请总结以下新闻：

{news_json}

请按照格式要求生成摘要。"""

_FALLBACK_MESSAGE = "今日暂无 AI 相关新闻，请稍后再关注。"
_LLM_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=60.0)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def summarize_news(
    items: list[dict],
    *,
    base_url: str,
    api_key: str,
    model: str,
) -> str:
    """Summarize a list of news items into a Chinese AI news digest.

    Args:
        items: List of news dicts with keys: title, link, summary, published_at.
        base_url: Base URL of the OpenAI-compatible API (e.g. https://api.openai.com).
        api_key: API key for authentication.
        model: Model name to use for completion.

    Returns:
        A Chinese summary string in the prescribed format.

    Raises:
        httpx.HTTPStatusError: On upstream HTTP error responses.
        httpx.RequestError: On network-level failures.
        RuntimeError: On malformed / unexpected API response structure.
    """
    if not items:
        return _FALLBACK_MESSAGE

    # Build user message — embed news as compact JSON
    news_for_prompt = [
        {
            "title": item["title"],
            "link": item["link"],
            "summary": item.get("summary", ""),
            "published_at": item.get("published_at", ""),
        }
        for item in items
    ]
    user_content = _USER_PROMPT_TEMPLATE.format(
        news_json=json.dumps(news_for_prompt, ensure_ascii=False, indent=2)
    )

    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.7,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=body, timeout=_LLM_TIMEOUT)

    # httpx raises HTTPStatusError for 4xx/5xx when raise_for_status is called;
    # we call it explicitly to get consistent behaviour.
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.error("LLM API returned error: %s", exc)
        raise

    data = response.json()

    # Defensive parsing of the expected structure
    try:
        choices = data["choices"]
    except KeyError:
        logger.error("LLM response missing 'choices' key: %s", data)
        raise RuntimeError("LLM API response missing 'choices' field") from None

    if not choices:
        raise RuntimeError("LLM API returned empty choices list")

    try:
        content = choices[0]["message"]["content"]
    except (KeyError, IndexError):
        logger.error("LLM response missing 'message.content': %s", choices)
        raise RuntimeError("LLM API response missing 'message.content' field") from None

    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("LLM API returned empty content")

    return content.strip()
