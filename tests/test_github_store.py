from pathlib import Path

from app.storage.github_store import GitHubStore
from collectors.github import GitHubRepoItem


def test_write_and_load_latest_snapshot(tmp_path: Path):
    store = GitHubStore(root_dir=tmp_path)
    items = [
        GitHubRepoItem(
            full_name="owner/repo",
            url="https://github.com/owner/repo",
            description="desc",
            stars=42,
            language="Python",
            fetched_at="2026-05-18T08:00:00",
        )
    ]

    store.write_snapshot(items, date_str="2026-05-18")
    loaded = store.load_latest_snapshot()

    assert loaded == items
    assert (tmp_path / "data" / "github" / "2026-05-18" / "repos.json").exists()
