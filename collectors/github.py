from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime

import httpx

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
_DEFAULT_BUDGET = 4

# 多查询召回：固定优先级，topics 优先
_QUERIES = [
    "topic:llm",
    "topic:agent",
    "topic:ai-tools",
    "topic:machine-learning",
    "ai agent",
    "llm tool",
    "developer tooling",
    "game ai",
]


class GitHubCollectorError(RuntimeError):
    """所有 GitHub query 全部失败时抛出。"""


@dataclass
class GitHubRepoItem:
    full_name: str
    url: str
    description: str = ""
    stars: int = 0
    forks: int = 0
    watchers: int = 0
    language: str = ""
    created_at: str = ""
    updated_at: str = ""
    pushed_at: str = ""
    matched_topics: list[str] = field(default_factory=list)
    matched_keywords: list[str] = field(default_factory=list)
    fetched_at: str = ""


def _read_budget() -> int:
    raw = os.getenv("GITHUB_QUERY_BUDGET", str(_DEFAULT_BUDGET)).strip()
    try:
        n = int(raw)
    except ValueError:
        n = _DEFAULT_BUDGET
    if n < 1:
        return _DEFAULT_BUDGET
    if n > len(_QUERIES):
        return len(_QUERIES)
    return n


class GitHubCollector:
    """GitHub Search API 多查询候选召回，带请求预算控制。

    每轮最多执行 budget 个 query（默认 4），按固定优先级截断。
    每 query 取 top 10，按 full_name 去重合并。
    """

    def __init__(self, max_per_query: int = 10, max_retries: int = 2, retry_delay: float = 0.5):
        self.max_per_query = max_per_query
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    async def collect(self) -> list[GitHubRepoItem]:
        headers = {"Accept": "application/vnd.github+json"}
        fetched_at = datetime.now().isoformat()
        raw_repos: dict[str, dict] = {}
        budget = _read_budget()
        queries = _QUERIES[:budget]
        success_count = 0
        last_error: Exception | None = None

        async with httpx.AsyncClient(timeout=15.0) as client:
            for query_str in queries:
                try:
                    repos = await self._fetch_query(client, query_str, headers)
                    success_count += 1
                except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                    last_error = exc
                    continue
                for repo in repos:
                    full_name = repo.get("full_name", "")
                    if full_name:
                        raw_repos[full_name] = repo

        if success_count == 0 and last_error is not None:
            raise GitHubCollectorError(f"all {len(queries)} GitHub queries failed") from last_error

        items = []
        for repo_data in raw_repos.values():
            items.append(
                GitHubRepoItem(
                    full_name=repo_data.get("full_name", ""),
                    url=repo_data.get("html_url", ""),
                    description=repo_data.get("description") or "",
                    stars=int(repo_data.get("stargazers_count", 0)),
                    forks=int(repo_data.get("forks_count", 0)),
                    watchers=int(repo_data.get("watchers_count", 0)),
                    language=repo_data.get("language") or "",
                    created_at=repo_data.get("created_at", ""),
                    updated_at=repo_data.get("updated_at", ""),
                    pushed_at=repo_data.get("pushed_at", ""),
                    matched_topics=_matched_topics(repo_data),
                    matched_keywords=_matched_keywords(repo_data),
                    fetched_at=fetched_at,
                )
            )
        return items

    async def _fetch_query(self, client: httpx.AsyncClient, q: str, headers: dict) -> list[dict]:
        params = {"q": q, "sort": "updated", "order": "desc", "per_page": self.max_per_query}
        attempts = self.max_retries + 1
        last_error: Exception | None = None

        for attempt in range(attempts):
            try:
                response = await client.get(GITHUB_SEARCH_URL, params=params, headers=headers)
                response.raise_for_status()
                return response.json().get("items", [])
            except httpx.TimeoutException as exc:
                last_error = exc
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code < 500:
                    raise
                last_error = exc
            if attempt < attempts - 1:
                await asyncio.sleep(self.retry_delay)

        assert last_error is not None
        raise last_error


def _matched_topics(repo_data: dict) -> list[str]:
    topics = repo_data.get("topics", [])
    if not isinstance(topics, list):
        return []
    relevant = {"llm", "agent", "ai-tools", "machine-learning"}
    return [t for t in topics if t in relevant]


def _matched_keywords(repo_data: dict) -> list[str]:
    keywords = ["ai agent", "llm", "developer tooling", "game ai"]
    text = " ".join(
        [
            repo_data.get("description", "") or "",
            repo_data.get("full_name", ""),
            " ".join(
                repo_data.get("topics", []) if isinstance(repo_data.get("topics"), list) else []
            ),
        ]
    ).lower()
    return [kw for kw in keywords if kw.lower() in text]
