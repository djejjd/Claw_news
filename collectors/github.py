from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import httpx

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
DEFAULT_QUERY = "topic:llm OR topic:artificial-intelligence OR topic:machine-learning"


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
        params = {
            "q": DEFAULT_QUERY,
            "sort": "stars",
            "order": "desc",
            "per_page": self.max_items,
        }
        headers = {"Accept": "application/vnd.github+json"}
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(GITHUB_SEARCH_URL, params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()

        fetched_at = datetime.now().isoformat()
        items: list[GitHubRepoItem] = []
        for repo in payload.get("items", [])[: self.max_items]:
            items.append(
                GitHubRepoItem(
                    full_name=repo.get("full_name", ""),
                    url=repo.get("html_url", ""),
                    description=repo.get("description") or "",
                    stars=int(repo.get("stargazers_count", 0)),
                    language=repo.get("language") or "",
                    fetched_at=fetched_at,
                )
            )
        return items
