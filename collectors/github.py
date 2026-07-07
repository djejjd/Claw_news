from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime

import httpx

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
DEFAULT_TOPICS = ("llm", "artificial-intelligence", "machine-learning")


@dataclass(eq=True)
class GitHubRepoItem:
    full_name: str
    url: str
    description: str
    stars: int
    language: str
    fetched_at: str


class GitHubCollector:
    def __init__(self, max_items: int = 3, max_retries: int = 2, retry_delay: float = 0.5):
        self.max_items = max_items
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    async def _fetch_topic(
        self,
        client: httpx.AsyncClient,
        topic: str,
        headers: dict[str, str],
    ) -> list[dict]:
        params = {
            "q": f"topic:{topic}",
            "sort": "stars",
            "order": "desc",
            "per_page": self.max_items,
        }
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

    async def collect(self) -> list[GitHubRepoItem]:
        headers = {"Accept": "application/vnd.github+json"}
        fetched_at = datetime.now().isoformat()
        raw_repos: dict[str, dict] = {}
        topic_successes = 0
        last_error: Exception | None = None

        async with httpx.AsyncClient(timeout=15.0) as client:
            for topic in DEFAULT_TOPICS:
                try:
                    repos = await self._fetch_topic(client, topic, headers)
                    topic_successes += 1
                except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                    last_error = exc
                    continue

                for repo in repos:
                    full_name = repo.get("full_name", "")
                    if full_name:
                        raw_repos[full_name] = repo

        if topic_successes == 0 and last_error is not None:
            raise last_error

        ranked = sorted(
            raw_repos.values(),
            key=lambda repo: int(repo.get("stargazers_count", 0)),
            reverse=True,
        )[: self.max_items]
        return [
            GitHubRepoItem(
                full_name=repo.get("full_name", ""),
                url=repo.get("html_url", ""),
                description=repo.get("description") or "",
                stars=int(repo.get("stargazers_count", 0)),
                language=repo.get("language") or "",
                fetched_at=fetched_at,
            )
            for repo in ranked
        ]
