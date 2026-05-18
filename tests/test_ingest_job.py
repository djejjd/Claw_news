from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_run_ingest_records_failed_sources_when_collector_raises():
    from app.scheduler.jobs import run_ingest

    failing_rss = MagicMock()
    failing_rss.collect = AsyncMock(side_effect=RuntimeError("rss down"))
    ok_hf = MagicMock()
    ok_hf.collect = AsyncMock(return_value=[])

    with (
        patch("collectors.rss_sources.RssCollector", return_value=failing_rss),
        patch("collectors.huggingface.HfDailyPapersCollector", return_value=ok_hf),
        patch("collectors.github.GitHubCollector.collect", new=AsyncMock(return_value=[])),
        patch("app.scheduler.jobs.IngestionStore"),
        patch("app.scheduler.jobs.GitHubStore"),
        patch("app.scheduler.jobs.IngestStatusStore") as status_store,
    ):
        await run_ingest()

    payload = status_store.return_value.write_status.call_args.args[0]
    assert payload["successful_sources"] == ["huggingface", "github"]
    assert payload["failed_sources"] == ["rss: rss down"]
