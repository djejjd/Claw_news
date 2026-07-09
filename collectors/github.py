from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime

import httpx

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"

# 多查询召回：topics + keywords
_TOPIC_QUERIES = [
    "topic:llm",
    "topic:agent",
    "topic:ai-tools",
    "topic:machine-learning",
]
_KEYWORD_QUERIES = [
    "ai agent",
    "llm tool",
    "developer tooling",
    "game ai",
]


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


class GitHubCollector:
    """GitHub Search API 多查询候选召回。

    每轮搜索多个 topic 和 keyword query，每查询取 top 10，
    按 full_name 去重合并，输出约 20-30 个候选。
    """

    def __init__(self, max_per_query: int = 10, max_retries: int = 2, retry_delay: float = 0.5):
        self.max_per_query = max_per_query
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    async def collect(self) -> list[GitHubRepoItem]:
        headers = {"Accept": "application/vnd.github+json"}
        fetched_at = datetime.now().isoformat()
        raw_repos: dict[str, dict] = {}
        queries = _TOPIC_QUERIES + _KEYWORD_QUERIES

        async with httpx.AsyncClient(timeout=15.0) as client:
            for query_str in queries:
                try:
                    repos = await self._fetch_query(client, query_str, headers)
                except (httpx.TimeoutException, httpx.HTTPStatusError):
                    continue
                for repo in repos:
                    full_name = repo.get("full_name", "")
                    if full_name:
                        raw_repos[full_name] = repo

        items = []
        for repo_data in raw_repos.values():
            items.append(GitHubRepoItem(
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
            ))
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
    text = " ".join([
        repo_data.get("description", "") or "",
        repo_data.get("full_name", ""),
        " ".join(repo_data.get("topics", []) if isinstance(repo_data.get("topics"), list) else []),
    ]).lower()
    return [kw for kw in keywords if kw.lower() in text]
