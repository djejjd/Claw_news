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

你必须严格按照以下 JSON 格式输出，不要输出任何其他内容：

{
  "headline_items": [
    {
      "title": "新闻标题（原文标题）",
      "url": "原文链接",
      "core_summary": "该新闻的核心内容，1-2句话",
      "importance": "高/中/低",
      "trend": "该新闻反映的行业趋势"
    }
  ],
  "daily_judgement": "用一句话总结今天的AI新闻整体态势",
  "github_projects": [
    {
      "full_name": "owner/repo",
      "description_cn": "将项目英文描述翻译为中文，1句话"
    }
  ]
}

要求：
- 只输出 JSON，不要用 ```json``` 包裹
- 每条新闻的 url 必须保留原文链接
- importance 只能是 高、中、低 三个值
- headline_items 按重要性从高到低排列
- github_projects 中的 description_cn 必须翻译为简洁的中文"""

_USER_PROMPT_TEMPLATE = """请总结以下新闻：

{news_json}

{github_section}

请按照格式要求生成摘要。"""

_FALLBACK_RESULT = {
    "headline_items": [],
    "daily_judgement": "今日暂无 AI 相关新闻，请稍后再关注。",
}
_LLM_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=60.0)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def parse_summary_result(raw_text: str) -> dict:
    """Parse LLM JSON output into structured dict, with fallback on failure.

    Returns a dict containing ``headline_items`` and ``daily_judgement``.
    On parse failure a degraded structure with ``_parse_error`` is returned;
    this function never raises.
    """
    text = raw_text.strip()
    # Strip ```json ... ``` fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

    try:
        data = json.loads(text)
        if "headline_items" not in data:
            raise ValueError("missing headline_items")
        if "daily_judgement" not in data:
            raise ValueError("missing daily_judgement")
        return data
    except (json.JSONDecodeError, ValueError) as e:
        return {
            "headline_items": [],
            "daily_judgement": raw_text[:500].strip(),
            "_parse_error": str(e),
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def summarize_news(
    items: list[dict],
    *,
    base_url: str,
    api_key: str,
    model: str,
    github_projects: list[dict] | None = None,
) -> dict:
    """Summarize a list of news items into a structured Chinese AI news digest.

    Args:
        items: List of news dicts with keys: title, link, summary, published_at.
        base_url: Base URL of the OpenAI-compatible API (e.g. https://api.openai.com).
        api_key: API key for authentication.
        model: Model name to use for completion.
        github_projects: Optional list of GitHub repo dicts with keys:
            full_name, description, stars, language.

    Returns:
        A dict with ``headline_items`` (list of news summaries),
        ``daily_judgement`` (one-line overall assessment), and
        ``github_projects`` (list of translated project descriptions).

    Raises:
        httpx.HTTPStatusError: On upstream HTTP error responses.
        httpx.RequestError: On network-level failures.
        RuntimeError: On malformed / unexpected API response structure.
    """
    if not items:
        return _FALLBACK_RESULT

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

    github_section = ""
    if github_projects:
        projects_for_prompt = [
            {
                "full_name": p["full_name"],
                "description": p.get("description", ""),
                "stars": p.get("stars", 0),
                "language": p.get("language", ""),
            }
            for p in github_projects
        ]
        github_section = (
            "以下是今日值得关注的 GitHub 项目，请将 description 翻译为中文：\n\n"
            f"{json.dumps(projects_for_prompt, ensure_ascii=False, indent=2)}"
        )

    user_content = _USER_PROMPT_TEMPLATE.format(
        news_json=json.dumps(news_for_prompt, ensure_ascii=False, indent=2),
        github_section=github_section,
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

    result = parse_summary_result(content)
    return result
