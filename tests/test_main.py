from pathlib import Path

import pytest

from collectors.base import HotItem


class StubPusher:
    def __init__(self, fail_category: str | None = None):
        self.fail_category = fail_category

    async def push_category(self, category, items, period="morning", pushed_urls=None):
        from pusher.wecom import PushResult

        if category == self.fail_category:
            return PushResult(
                category=category, success=False, urls=[], errcode=45009, errmsg="rate limited"
            )
        return PushResult(
            category=category,
            success=True,
            urls=[item.url for item in items if item.url],
            errcode=0,
            errmsg="ok",
        )


@pytest.mark.asyncio
async def test_successful_categories_committed_even_if_later_one_fails(tmp_path: Path):
    from infra.storage.state_store import StateStore
    from main import run_push_sequence

    grouped = {
        "ai": [HotItem("AI", "https://a.com/1", "", "qbitai", "ai", 5.0)],
        "game": [HotItem("Game", "https://g.com/1", "", "yystv", "game", 5.0)],
        "device": [HotItem("Device", "https://d.com/1", "", "ithome", "device", 5.0)],
    }
    store = StateStore(tmp_path)

    await run_push_sequence(
        grouped=grouped,
        period="morning",
        pushed_urls=store.load_pushed_urls(),
        state_store=store,
        pusher=StubPusher(fail_category="device"),
    )

    saved = store.load_pushed_urls()
    assert "https://a.com/1" in saved
    assert "https://g.com/1" in saved
    assert "https://d.com/1" not in saved
