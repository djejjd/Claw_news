from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.pipeline.candidate import CandidateItem
from collectors.github import GitHubCollectorError
from collectors.base import HotItem


def _make_candidate(**kwargs) -> CandidateItem:
    data = {
        "title": "AI Title",
        "url": "https://example.com/ai",
        "summary": "A sufficiently long AI summary for acceptance.",
        "source": "test",
        "category": "ai",
    }
    data.update(kwargs)
    return CandidateItem(**data)


def _make_hotitem(**kwargs) -> HotItem:
    data = {
        "title": "AI Title",
        "url": "https://example.com/ai",
        "summary": "A sufficiently long AI summary for acceptance.",
        "source": "rss",
        "category": "ai",
        "source_score": 5.0,
    }
    data.update(kwargs)
    return HotItem(**data)


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
        patch("collectors.taptap.TapTapCollector", return_value=ok_hf),
        patch("collectors.github.GitHubCollector.collect", new=AsyncMock(return_value=[])),
        patch("app.scheduler.jobs.IngestionStore"),
        patch("app.scheduler.jobs.GitHubStore"),
        patch("app.scheduler.jobs.IngestStatusStore") as status_store,
    ):
        await run_ingest()

    payload = status_store.return_value.write_status.call_args.args[0]
    assert payload["successful_sources"] == ["huggingface", "taptap", "github"]
    assert payload["failed_sources"] == ["rss: rss down"]
    assert payload["skipped_sources"] == []


@pytest.mark.asyncio
async def test_run_ingest_skips_optional_huggingface_failures(monkeypatch):
    from app.scheduler.jobs import run_ingest

    monkeypatch.setenv("HF_OPTIONAL", "1")

    ok_rss = MagicMock()
    ok_rss.collect = AsyncMock(return_value=[])
    failing_hf = MagicMock()
    failing_hf.collect = AsyncMock(side_effect=RuntimeError("hf timeout"))

    with (
        patch("collectors.rss_sources.RssCollector", return_value=ok_rss),
        patch("collectors.huggingface.HfDailyPapersCollector", return_value=failing_hf),
        patch("collectors.taptap.TapTapCollector", return_value=ok_rss),
        patch("collectors.github.GitHubCollector.collect", new=AsyncMock(return_value=[])),
        patch("app.scheduler.jobs.IngestionStore"),
        patch("app.scheduler.jobs.GitHubStore"),
        patch("app.scheduler.jobs.IngestStatusStore") as status_store,
    ):
        await run_ingest()

    payload = status_store.return_value.write_status.call_args.args[0]
    assert payload["successful_sources"] == ["rss", "taptap", "github"]
    assert payload["failed_sources"] == []
    assert payload["skipped_sources"] == ["huggingface: hf timeout"]


@pytest.mark.asyncio
async def test_run_ingest_skips_optional_taptap_failures(monkeypatch):
    from app.scheduler.jobs import run_ingest

    monkeypatch.setenv("TAPTAP_OPTIONAL", "1")

    ok_rss = MagicMock()
    ok_rss.collect = AsyncMock(return_value=[])
    ok_hf = MagicMock()
    ok_hf.collect = AsyncMock(return_value=[])
    failing_taptap = MagicMock()
    failing_taptap.collect = AsyncMock(side_effect=RuntimeError("taptap blocked"))

    with (
        patch("collectors.rss_sources.RssCollector", return_value=ok_rss),
        patch("collectors.huggingface.HfDailyPapersCollector", return_value=ok_hf),
        patch("collectors.taptap.TapTapCollector", return_value=failing_taptap),
        patch("collectors.github.GitHubCollector.collect", new=AsyncMock(return_value=[])),
        patch("app.scheduler.jobs.IngestionStore"),
        patch("app.scheduler.jobs.GitHubStore"),
        patch("app.scheduler.jobs.IngestStatusStore") as status_store,
    ):
        await run_ingest()

    payload = status_store.return_value.write_status.call_args.args[0]
    assert payload["successful_sources"] == ["rss", "huggingface", "github"]
    assert payload["failed_sources"] == []
    assert payload["skipped_sources"] == ["taptap: taptap blocked"]


@pytest.mark.asyncio
async def test_run_ingest_marks_github_failed_when_all_queries_fail():
    from app.scheduler.jobs import run_ingest

    ok_rss = MagicMock()
    ok_rss.collect = AsyncMock(return_value=[])
    github_error = GitHubCollectorError("all 4 GitHub queries failed")

    with (
        patch("collectors.rss_sources.RssCollector", return_value=ok_rss),
        patch("collectors.huggingface.HfDailyPapersCollector", return_value=ok_rss),
        patch("collectors.taptap.TapTapCollector", return_value=ok_rss),
        patch("collectors.github.GitHubCollector.collect", new=AsyncMock(side_effect=github_error)),
        patch("app.scheduler.jobs.IngestionStore"),
        patch("app.scheduler.jobs.GitHubStore"),
        patch("app.scheduler.jobs.IngestStatusStore") as status_store,
    ):
        await run_ingest()

    payload = status_store.return_value.write_status.call_args.args[0]
    assert "github" not in payload["successful_sources"]
    assert payload["failed_sources"] == ["github: all 4 GitHub queries failed"]
    assert payload["skipped_sources"] == []


@pytest.mark.asyncio
async def test_run_ingest_preloads_recent_keys_dedups_before_quality_and_updates_state():
    from app.scheduler.jobs import run_ingest

    duplicate_key = CandidateItem.make_canonical_key("https://dup.example.com/a")
    rss_items = [
        _make_hotitem(
            title="Duplicate candidate",
            url="https://dup.example.com/a",
            summary="A sufficiently long AI summary for acceptance.",
            source="qbitai",
        ),
        _make_hotitem(
            title="Fresh candidate",
            url="https://fresh.example.com/a",
            summary="A sufficiently long AI summary for acceptance.",
            source="qbitai",
        ),
    ]

    rss_collector = MagicMock()
    rss_collector.collect = AsyncMock(return_value=rss_items)
    hf_collector = MagicMock()
    hf_collector.collect = AsyncMock(return_value=[])

    ingestion_store = MagicMock()
    ingestion_store.load_recent_seen_canonical_keys.return_value = {duplicate_key}
    ingestion_store.append_or_merge.return_value = {"item_count": 1}

    metrics_store = MagicMock()
    metrics_store.aggregate_recent.side_effect = [
        {
            "source": "rss",
            "runs": 12,
            "raw_fetched_count": 2,
            "accepted_count": 1,
            "selected_count": 0,
            "effective_new_rate": 0.9,
            "selection_rate": 0.9,
        },
        {
            "source": "huggingface",
            "runs": 12,
            "raw_fetched_count": 0,
            "accepted_count": 0,
            "selected_count": 0,
            "effective_new_rate": 0.0,
            "selection_rate": 0.0,
        },
        {
            "source": "taptap",
            "runs": 12,
            "raw_fetched_count": 0,
            "accepted_count": 0,
            "selected_count": 0,
            "effective_new_rate": 0.0,
            "selection_rate": 0.0,
        },
    ]

    state_store = MagicMock()
    state_store.load_state.side_effect = [
        {
            "source": "rss",
            "fetch_count": 7,
            "min_fetch_count": 5,
            "max_fetch_count": 10,
            "cooldown_remaining": 0,
            "last_adjusted_at": None,
        },
        {
            "source": "huggingface",
            "fetch_count": 4,
            "min_fetch_count": 4,
            "max_fetch_count": 4,
            "cooldown_remaining": 0,
            "last_adjusted_at": None,
        },
        {
            "source": "taptap",
            "fetch_count": 3,


            "min_fetch_count": 3,
            "max_fetch_count": 3,
            "cooldown_remaining": 0,
            "last_adjusted_at": None,
        },
    ]

    with (
        patch("collectors.rss_sources.RssCollector", return_value=rss_collector) as rss_cls,
        patch("collectors.huggingface.HfDailyPapersCollector", return_value=hf_collector) as hf_cls,
        patch("collectors.taptap.TapTapCollector", return_value=MagicMock(collect=AsyncMock(return_value=[]))) as taptap_cls,
        patch("collectors.github.GitHubCollector.collect", new=AsyncMock(return_value=[])),
        patch("app.scheduler.jobs.IngestionStore", return_value=ingestion_store, create=True),
        patch("app.scheduler.jobs.SourceMetricsStore", return_value=metrics_store, create=True),
        patch("app.scheduler.jobs.SourceStateStore", return_value=state_store, create=True),
        patch(
            "app.scheduler.jobs.should_accept_candidate", side_effect=lambda item: True, create=True
        ) as accept_mock,
    ):
        result = await run_ingest()

    assert result["item_count"] == 1
    ingestion_store.load_recent_seen_canonical_keys.assert_called_once()
    assert rss_cls.call_args.kwargs["fetch_count"] == 7
    assert hf_cls.call_args.kwargs["fetch_count"] == 4
    assert taptap_cls.call_args.kwargs["fetch_count"] == 3
    assert metrics_store.append_run_metric.call_count == 3
    assert state_store.save_state.call_count == 3
    assert ingestion_store.append_or_merge.call_args.args[0][0].url == "https://fresh.example.com/a"
    assert accept_mock.call_count == 1
    rss_save_call = state_store.save_state.call_args_list[0]
    assert rss_save_call.args[0] == "rss"
    assert rss_save_call.args[1]["fetch_count"] == 9


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("first_summary", "second_summary", "expected_accepted_count"),
    [
        ("short", "A sufficiently long AI summary for acceptance.", 0),
        ("A sufficiently long AI summary for acceptance.", "short", 1),
    ],
)
async def test_run_ingest_dedups_same_round_before_quality_filter(
    first_summary, second_summary, expected_accepted_count
):
    from app.scheduler.jobs import run_ingest

    same_key = CandidateItem.make_canonical_key("https://dup.example.com/a")
    rss_items = [
        _make_hotitem(
            title="First candidate",
            url="https://dup.example.com/a",
            summary=first_summary,
            source="qbitai",
        ),
        _make_hotitem(
            title="Second candidate",
            url="https://dup.example.com/a",
            summary=second_summary,
            source="qbitai",
        ),
    ]

    rss_collector = MagicMock()
    rss_collector.collect = AsyncMock(return_value=rss_items)
    hf_collector = MagicMock()
    hf_collector.collect = AsyncMock(return_value=[])

    ingestion_store = MagicMock()
    ingestion_store.load_recent_seen_canonical_keys.return_value = set()
    ingestion_store.append_or_merge.return_value = {"item_count": expected_accepted_count}

    metrics_store = MagicMock()
    metrics_store.aggregate_recent.side_effect = [
        {
            "source": "rss",
            "runs": 12,
            "raw_fetched_count": 2,
            "accepted_count": expected_accepted_count,
            "selected_count": 0,
            "effective_new_rate": 0.5,
            "selection_rate": 0.5,
        },
        {
            "source": "huggingface",
            "runs": 12,
            "raw_fetched_count": 0,
            "accepted_count": 0,
            "selected_count": 0,
            "effective_new_rate": 0.0,
            "selection_rate": 0.0,
        },
        {
            "source": "taptap",
            "runs": 12,
            "raw_fetched_count": 0,
            "accepted_count": 0,
            "selected_count": 0,
            "effective_new_rate": 0.0,
            "selection_rate": 0.0,
        },
    ]

    state_store = MagicMock()
    state_store.load_state.side_effect = [
        {
            "source": "rss",
            "fetch_count": 2,
            "min_fetch_count": 2,
            "max_fetch_count": 2,
            "cooldown_remaining": 0,
            "last_adjusted_at": None,
        },
        {
            "source": "huggingface",
            "fetch_count": 2,
            "min_fetch_count": 2,
            "max_fetch_count": 2,
            "cooldown_remaining": 0,
            "last_adjusted_at": None,
        },
        {
            "source": "taptap",
            "fetch_count": 2,
            "min_fetch_count": 2,
            "max_fetch_count": 2,
            "cooldown_remaining": 0,
            "last_adjusted_at": None,
        },
    ]

    def accept_if_long_enough(item):
        return len(item.summary.strip()) >= 20

    with (
        patch("collectors.rss_sources.RssCollector", return_value=rss_collector),
        patch("collectors.huggingface.HfDailyPapersCollector", return_value=hf_collector),
        patch("collectors.taptap.TapTapCollector", return_value=MagicMock(collect=AsyncMock(return_value=[]))),
        patch("collectors.github.GitHubCollector.collect", new=AsyncMock(return_value=[])),
        patch("app.scheduler.jobs.IngestionStore", return_value=ingestion_store, create=True),
        patch("app.scheduler.jobs.SourceMetricsStore", return_value=metrics_store, create=True),
        patch("app.scheduler.jobs.SourceStateStore", return_value=state_store, create=True),
        patch(
            "app.scheduler.jobs.should_accept_candidate", side_effect=accept_if_long_enough
        ) as accept_mock,
    ):
        result = await run_ingest()

    assert accept_mock.call_count == 1
    assert result["item_count"] == expected_accepted_count
    if expected_accepted_count:
        assert ingestion_store.append_or_merge.call_args.args[0]
        assert ingestion_store.append_or_merge.call_args.args[0][0].canonical_key == same_key
    else:
        assert ingestion_store.append_or_merge.call_count == 0


@pytest.mark.asyncio
async def test_run_ingest_accepts_tool_and_game_candidates():
    from app.scheduler.jobs import run_ingest

    rss_items = [
        _make_hotitem(title="AI Item", url="https://a.com/1", summary="Long enough AI summary text for acceptance.", source="qbitai", category="ai"),
        _make_hotitem(title="Tool Item", url="https://t.com/1", summary="Long enough tool summary text for acceptance.", source="sspai", category="tool"),
        _make_hotitem(title="Game Item", url="https://g.com/1", summary="Long enough game summary text for acceptance.", source="yystv", category="game"),
    ]

    rss_collector = MagicMock()
    rss_collector.collect = AsyncMock(return_value=rss_items)
    hf_collector = MagicMock()
    hf_collector.collect = AsyncMock(return_value=[])
    taptap_collector = MagicMock()
    taptap_collector.collect = AsyncMock(return_value=[])

    ingestion_store = MagicMock()
    ingestion_store.load_recent_seen_canonical_keys.return_value = set()
    ingestion_store.append_or_merge.return_value = {"item_count": 3}

    metrics_store = MagicMock()
    metrics_store.aggregate_recent.side_effect = [
        {"source": "rss", "runs": 24, "effective_new_rate": 0.5, "selection_rate": 0.3, "raw_fetched_count": 3, "accepted_count": 3, "selected_count": 0},
        {"source": "huggingface", "runs": 24, "effective_new_rate": 0.0, "selection_rate": 0.0, "raw_fetched_count": 0, "accepted_count": 0, "selected_count": 0},
        {"source": "taptap", "runs": 24, "effective_new_rate": 0.0, "selection_rate": 0.0, "raw_fetched_count": 0, "accepted_count": 0, "selected_count": 0},
    ]

    state_store = MagicMock()
    state_store.load_state.side_effect = [
        {"source": "rss", "fetch_count": 5, "min_fetch_count": 5, "max_fetch_count": 5, "cooldown_remaining": 0},
        {"source": "huggingface", "fetch_count": 2, "min_fetch_count": 2, "max_fetch_count": 2, "cooldown_remaining": 0},
        {"source": "taptap", "fetch_count": 3, "min_fetch_count": 3, "max_fetch_count": 3, "cooldown_remaining": 0},
    ]

    with (
        patch("collectors.rss_sources.RssCollector", return_value=rss_collector),
        patch("collectors.huggingface.HfDailyPapersCollector", return_value=hf_collector),
        patch("collectors.taptap.TapTapCollector", return_value=taptap_collector),
        patch("collectors.github.GitHubCollector.collect", new=AsyncMock(return_value=[])),
        patch("app.scheduler.jobs.IngestionStore", return_value=ingestion_store, create=True),
        patch("app.scheduler.jobs.SourceMetricsStore", return_value=metrics_store, create=True),
        patch("app.scheduler.jobs.SourceStateStore", return_value=state_store, create=True),
        patch("app.scheduler.jobs.should_accept_candidate", side_effect=lambda item: True, create=True),
    ):
        result = await run_ingest()

    assert result["item_count"] == 3
    saved = ingestion_store.append_or_merge.call_args.args[0]
    assert {item.category for item in saved} == {"ai", "tool", "game"}


def test_should_accept_candidate_rejects_short_summary():
    from app.ingest.source_policy import should_accept_candidate

    item = _make_candidate(summary="ab")

    assert should_accept_candidate(item) is False


def test_should_accept_candidate_accepts_summary_at_min_length():
    from app.ingest.source_policy import should_accept_candidate

    item = _make_candidate(summary="x" * 5)

    assert should_accept_candidate(item) is True


def test_should_accept_candidate_rejects_empty_title():
    from app.ingest.source_policy import should_accept_candidate

    item = _make_candidate(title="   ")

    assert should_accept_candidate(item) is False


def test_should_accept_candidate_rejects_empty_url():
    from app.ingest.source_policy import should_accept_candidate

    item = _make_candidate(url="   ")

    assert should_accept_candidate(item) is False


def test_should_accept_candidate_rejects_unknown_category():
    from app.ingest.source_policy import should_accept_candidate

    item = _make_candidate(category="unknown_cat")

    assert should_accept_candidate(item) is False


def test_should_accept_candidate_accepts_ai_tool_game_categories():
    from app.ingest.source_policy import should_accept_candidate

    for cat in ("ai", "tool", "game"):
        item = _make_candidate(category=cat)
        assert should_accept_candidate(item) is True, f"category '{cat}' should be accepted"


def test_should_accept_candidate_accepts_valid_ai_candidate():
    from app.ingest.source_policy import should_accept_candidate

    item = _make_candidate()

    assert should_accept_candidate(item) is True


def test_update_fetch_count_from_metrics_increases_and_enters_cooldown():
    from app.ingest.source_policy import update_fetch_count_from_metrics

    state = {
        "fetch_count": 10,
        "min_fetch_count": 6,
        "max_fetch_count": 20,
        "cooldown_remaining": 0,
        "last_adjusted_at": None,
    }
    metrics = {
        "runs": 12,
        "effective_new_rate": 0.5,
        "selection_rate": 0.2,
    }

    updated = update_fetch_count_from_metrics(state, metrics, "2026-05-19T10:00:00")

    assert updated["fetch_count"] == 12
    assert updated["cooldown_remaining"] == 6
    assert updated["last_adjusted_at"] == "2026-05-19T10:00:00"


def test_update_fetch_count_from_metrics_decreases_and_enters_cooldown():
    from app.ingest.source_policy import update_fetch_count_from_metrics

    state = {
        "fetch_count": 10,
        "min_fetch_count": 6,
        "max_fetch_count": 20,
        "cooldown_remaining": 0,
        "last_adjusted_at": None,
    }
    metrics = {
        "runs": 12,
        "effective_new_rate": 0.1,
        "selection_rate": 0.9,
    }

    updated = update_fetch_count_from_metrics(state, metrics, "2026-05-19T10:00:00")

    assert updated["fetch_count"] == 8
    assert updated["cooldown_remaining"] == 6
    assert updated["last_adjusted_at"] == "2026-05-19T10:00:00"


def test_update_fetch_count_from_metrics_neutral_branch_does_not_adjust():
    from app.ingest.source_policy import update_fetch_count_from_metrics

    state = {
        "fetch_count": 10,
        "min_fetch_count": 6,
        "max_fetch_count": 20,
        "cooldown_remaining": 0,
        "last_adjusted_at": "2026-05-19T09:00:00",
    }
    metrics = {
        "runs": 12,
        "effective_new_rate": 0.3,
        "selection_rate": 0.1,
    }

    updated = update_fetch_count_from_metrics(state, metrics, "2026-05-19T10:00:00")

    assert updated["fetch_count"] == 10
    assert updated["cooldown_remaining"] == 0
    assert updated["last_adjusted_at"] == "2026-05-19T09:00:00"


def test_update_fetch_count_from_metrics_respects_cooldown_and_bounds():
    from app.ingest.source_policy import update_fetch_count_from_metrics

    cooling_state = {
        "fetch_count": 4,
        "min_fetch_count": 6,
        "max_fetch_count": 20,
        "cooldown_remaining": 3,
        "last_adjusted_at": "2026-05-19T09:00:00",
    }
    cooling_metrics = {
        "runs": 20,
        "effective_new_rate": 0.9,
        "selection_rate": 0.9,
    }

    cooling_updated = update_fetch_count_from_metrics(
        cooling_state, cooling_metrics, "2026-05-19T10:00:00"
    )

    assert cooling_updated["fetch_count"] == 6
    assert cooling_updated["cooldown_remaining"] == 2
    assert cooling_updated["last_adjusted_at"] == "2026-05-19T09:00:00"

    max_state = {
        "fetch_count": 20,
        "min_fetch_count": 6,
        "max_fetch_count": 20,
        "cooldown_remaining": 0,
        "last_adjusted_at": None,
    }
    min_state = {
        "fetch_count": 6,
        "min_fetch_count": 6,
        "max_fetch_count": 20,
        "cooldown_remaining": 0,
        "last_adjusted_at": None,
    }
    high_metrics = {
        "runs": 12,
        "effective_new_rate": 0.9,
        "selection_rate": 0.9,
    }
    low_metrics = {
        "runs": 12,
        "effective_new_rate": 0.0,
        "selection_rate": 0.9,
    }

    max_updated = update_fetch_count_from_metrics(max_state, high_metrics, "2026-05-19T10:00:00")
    min_updated = update_fetch_count_from_metrics(min_state, low_metrics, "2026-05-19T10:00:00")

    assert max_updated["fetch_count"] == 20
    assert max_updated["cooldown_remaining"] == 0
    assert min_updated["fetch_count"] == 6
    assert min_updated["cooldown_remaining"] == 0


def test_update_fetch_count_from_metrics_no_cooldown_when_clamped_no_change():
    from app.ingest.source_policy import update_fetch_count_from_metrics

    state = {
        "fetch_count": 20,
        "min_fetch_count": 6,
        "max_fetch_count": 20,
        "cooldown_remaining": 0,
        "last_adjusted_at": "2026-05-19T09:00:00",
    }
    metrics = {
        "runs": 12,
        "effective_new_rate": 0.9,
        "selection_rate": 0.9,
    }

    updated = update_fetch_count_from_metrics(state, metrics, "2026-05-19T10:00:00")

    assert updated["fetch_count"] == 20
    assert updated["cooldown_remaining"] == 0
    assert updated["last_adjusted_at"] == "2026-05-19T09:00:00"


def test_update_fetch_count_from_metrics_clamps_out_of_bounds_when_runs_too_low():
    from app.ingest.source_policy import update_fetch_count_from_metrics

    state = {
        "fetch_count": 4,
        "min_fetch_count": 6,
        "max_fetch_count": 20,
        "cooldown_remaining": 0,
        "last_adjusted_at": "2026-05-19T09:00:00",
    }
    metrics = {
        "runs": 11,
        "effective_new_rate": 0.9,
        "selection_rate": 0.9,
    }

    updated = update_fetch_count_from_metrics(state, metrics, "2026-05-19T10:00:00")

    assert updated["fetch_count"] == 6
    assert updated["cooldown_remaining"] == 0
    assert updated["last_adjusted_at"] == "2026-05-19T09:00:00"


@pytest.mark.asyncio
async def test_run_ingest_cleanup_prunes_at_7_days():
    """run_ingest_with_cleanup 以 keep_days=7 调用 prune_expired（Task 3）。"""
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.scheduler.jobs import run_ingest_with_cleanup

    with (
        patch("app.scheduler.jobs.run_ingest", new=AsyncMock()),
        patch("app.scheduler.jobs.IngestionStore") as store_cls,
    ):
        mock_store = MagicMock()
        store_cls.return_value = mock_store
        await run_ingest_with_cleanup()

    mock_store.prune_expired.assert_called_once_with(keep_days=7)
