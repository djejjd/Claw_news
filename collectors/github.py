from __future__ import annotations

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
    def __init__(self, max_items: int = 3):
        self.max_items = max_items

    async def collect(self) -> list[GitHubRepoItem]:
        headers = {"Accept": "application/vnd.github+json"}
        fetched_at = datetime.now().isoformat()
        raw_repos: dict[str, dict] = {}

        async with httpx.AsyncClient(timeout=15.0) as client:
            for topic in DEFAULT_TOPICS:
                params = {
                    "q": f"topic:{topic}",
                    "sort": "stars",
                    "order": "desc",
                    "per_page": self.max_items,
                }
                response = await client.get(GITHUB_SEARCH_URL, params=params, headers=headers)
                response.raise_for_status()
                for repo in response.json().get("items", []):
                    full_name = repo.get("full_name", "")
                    if full_name:
                        raw_repos[full_name] = repo

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
