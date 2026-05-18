from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path

from app.pipeline.candidate import CandidateItem
from app.storage.ingestion_store import IngestionStore


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_item(title="T", url="https://x.com/a", summary="S", source="test",
               category="ai", **kwargs) -> CandidateItem:
    key = kwargs.pop("canonical_key", CandidateItem.make_canonical_key(url))
    fetched = kwargs.pop("fetched_at", datetime.now().isoformat())
    return CandidateItem(
        title=title, url=url, summary=summary, source=source,
        category=category, canonical_key=key, fetched_at=fetched, **kwargs,
    )


def _make_dict_item(**kwargs) -> dict:
    """Return a plain dict that passes through normalize."""
    return kwargs


def _write_jsonl(day_dir: Path, items: list[CandidateItem]) -> None:
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / "candidates.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")


def _today_str() -> str:
    return date.today().isoformat()


# ---------------------------------------------------------------------------
# append_or_merge
# ---------------------------------------------------------------------------

class TestAppendOrMerge:
    def test_creates_dir_and_files(self, tmp_path: Path):
        store = IngestionStore(root_dir=tmp_path)
        items = [_make_item(title="Hello", url="https://a.com/1")]
        result = store.append_or_merge(items)

        today = _today_str()
        day_dir = tmp_path / "data" / "ingestion" / today
        assert day_dir.is_dir()
        assert (day_dir / "candidates.jsonl").exists()
        assert (day_dir / "index.json").exists()

        assert result["date"] == today
        assert result["item_count"] == 1
        assert "a.com/1" in result["seen_keys"]

    def test_appends_distinct_keys(self, tmp_path: Path):
        store = IngestionStore(root_dir=tmp_path)
        i1 = _make_item(url="https://a.com/1")
        i2 = _make_item(url="https://b.com/2")

        store.append_or_merge([i1])
        result = store.append_or_merge([i2])

        assert result["item_count"] == 2
        assert len(result["seen_keys"]) == 2

        # JSONL 应有 2 行
        day_dir = tmp_path / "data" / "ingestion" / _today_str()
        lines = (day_dir / "candidates.jsonl").read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2

    def test_same_key_appends_multiple_lines(self, tmp_path: Path):
        """同一 canonical_key 允许多条追加，JSONL 中保留多条。"""
        store = IngestionStore(root_dir=tmp_path)
        i1 = _make_item(url="https://a.com/1", summary="v1")
        i2 = _make_item(url="https://a.com/1", summary="v2")

        store.append_or_merge([i1])
        result = store.append_or_merge([i2])

        # seen_keys 去重
        assert len(result["seen_keys"]) == 1
        assert result["item_count"] == 2

        # JSONL 有 2 行
        day_dir = tmp_path / "data" / "ingestion" / _today_str()
        lines = (day_dir / "candidates.jsonl").read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        assert "v1" in lines[0]
        assert "v2" in lines[1]

    def test_dict_items_are_normalized(self, tmp_path: Path):
        store = IngestionStore(root_dir=tmp_path)
        d = {
            "title": "D", "url": "https://d.com/p",
            "summary": "sd", "source": "test", "category": "ai",
        }
        result = store.append_or_merge([d])
        assert result["item_count"] == 1

        # 应生成了 canonical_key
        day_dir = tmp_path / "data" / "ingestion" / _today_str()
        lines = (day_dir / "candidates.jsonl").read_text(encoding="utf-8").strip().split("\n")
        data = json.loads(lines[0])
        assert data["canonical_key"] == "d.com/p"

    def test_source_failures_accumulate(self, tmp_path: Path):
        store = IngestionStore(root_dir=tmp_path)
        store.append_or_merge([_make_item()], source_failures=["s1"])
        result = store.append_or_merge([_make_item(url="https://b.com")], source_failures=["s2", "s1"])
        assert set(result["source_failures"]) == {"s1", "s2"}

    def test_index_json_structure(self, tmp_path: Path):
        store = IngestionStore(root_dir=tmp_path)
        result = store.append_or_merge(
            [_make_item(url="https://x.com/1")],
            source_failures=["bad_source"],
        )

        assert set(result.keys()) == {"date", "seen_keys", "source_failures", "item_count", "updated_at"}
        assert isinstance(result["date"], str)
        assert isinstance(result["seen_keys"], list)
        assert isinstance(result["source_failures"], list)
        assert isinstance(result["item_count"], int)
        assert isinstance(result["updated_at"], str)

    def test_index_persisted_and_reloaded(self, tmp_path: Path):
        store = IngestionStore(root_dir=tmp_path)
        store.append_or_merge([_make_item(url="https://z.com/1")])

        # 从磁盘读取 index 验证持久化
        day_dir = tmp_path / "data" / "ingestion" / _today_str()
        on_disk = json.loads((day_dir / "index.json").read_text(encoding="utf-8"))
        assert on_disk["item_count"] == 1
        assert len(on_disk["seen_keys"]) == 1

    def test_empty_items_list(self, tmp_path: Path):
        store = IngestionStore(root_dir=tmp_path)
        result = store.append_or_merge([])
        assert result["item_count"] == 0
        assert result["seen_keys"] == []


# ---------------------------------------------------------------------------
# load_window_candidates
# ---------------------------------------------------------------------------

class TestLoadWindowCandidates:
    def test_folds_by_canonical_key(self, tmp_path: Path):
        """同 key 多条记录时折叠为一条。"""
        store = IngestionStore(root_dir=tmp_path)

        # 使用 append_or_merge 写入同一天的同 key 两条
        i1 = _make_item(url="https://k.com/1", summary="shorter")
        i2 = _make_item(url="https://k.com/1", summary="longer summary here")
        store.append_or_merge([i1])
        store.append_or_merge([i2])

        today = _today_str()
        candidates = store.load_window_candidates(
            time_window_start=f"{today}T00:00:00",
            time_window_end=f"{today}T23:59:59",
        )
        assert len(candidates) == 1
        # 默认 fetched_at 相同，按 summary 长度 -> 选更长的
        assert candidates[0].summary == "longer summary here"

    def test_priority_published_at(self, tmp_path: Path):
        """published_at 更新的优先。"""
        store = IngestionStore(root_dir=tmp_path)

        old = _make_item(url="https://p.com/1", published_at="2026-05-10", summary="old pub")
        new = _make_item(url="https://p.com/1", published_at="2026-05-15", summary="new pub")
        store.append_or_merge([old])
        store.append_or_merge([new])

        today = _today_str()
        candidates = store.load_window_candidates(
            time_window_start=f"{today}T00:00:00",
            time_window_end=f"{today}T23:59:59",
        )
        assert len(candidates) == 1
        assert candidates[0].published_at == "2026-05-15"

    def test_priority_fetched_at(self, tmp_path: Path):
        """published_at 相同或缺失时 fetched_at 更新的优先。"""
        store = IngestionStore(root_dir=tmp_path)

        t1 = "2026-05-18T08:00:00"
        t2 = "2026-05-18T09:00:00"
        early = _make_item(url="https://f.com/1", fetched_at=t1, summary="early")
        late = _make_item(url="https://f.com/1", fetched_at=t2, summary="late")
        store.append_or_merge([early])
        store.append_or_merge([late])

        today = _today_str()
        candidates = store.load_window_candidates(
            time_window_start=f"{today}T00:00:00",
            time_window_end=f"{today}T23:59:59",
        )
        assert len(candidates) == 1
        assert candidates[0].fetched_at == t2

    def test_priority_summary_length_fallback(self, tmp_path: Path):
        """published_at 和 fetched_at 都相同时按 summary 长度。"""
        store = IngestionStore(root_dir=tmp_path)
        t = "2026-05-18T08:00:00"

        short = _make_item(url="https://s.com/1", fetched_at=t, summary="sh")
        long_ = _make_item(url="https://s.com/1", fetched_at=t, summary="longer summary text")
        store.append_or_merge([short])
        store.append_or_merge([long_])

        today = _today_str()
        candidates = store.load_window_candidates(
            time_window_start=f"{today}T00:00:00",
            time_window_end=f"{today}T23:59:59",
        )
        assert len(candidates) == 1
        assert candidates[0].summary == "longer summary text"

    def test_time_window_filter(self, tmp_path: Path):
        """只加载时间窗口内的目录。"""
        store = IngestionStore(root_dir=tmp_path)

        today = date.today()
        d1 = today.isoformat()
        d2 = (today - timedelta(days=1)).isoformat()
        d3 = (today - timedelta(days=3)).isoformat()

        ing = tmp_path / "data" / "ingestion"

        _write_jsonl(ing / d1, [_make_item(url="https://inside.com/1", summary="today")])
        _write_jsonl(ing / d2, [_make_item(url="https://inside.com/2", summary="yday")])
        _write_jsonl(ing / d3, [_make_item(url="https://outside.com/1", summary="old")])

        # 窗口只覆盖 d2..d1（最近两天）
        candidates = store.load_window_candidates(
            time_window_start=f"{d2}T00:00:00",
            time_window_end=f"{d1}T23:59:59",
        )
        summaries = {c.summary for c in candidates}
        assert "today" in summaries
        assert "yday" in summaries
        assert "old" not in summaries

    def test_time_window_filter_excludes_same_day_items_after_window_end(self, tmp_path: Path):
        """同一目录内，fetched_at 超出窗口结束时刻的候选也必须被排除。"""
        store = IngestionStore(root_dir=tmp_path)
        today = _today_str()
        ing = tmp_path / "data" / "ingestion"

        inside = _make_item(
            url="https://inside.com/within-window",
            summary="inside",
            fetched_at=f"{today}T08:00:00",
        )
        outside = _make_item(
            url="https://outside.com/after-window",
            summary="outside",
            fetched_at=f"{today}T12:00:00",
        )
        _write_jsonl(ing / today, [inside, outside])

        candidates = store.load_window_candidates(
            time_window_start=f"{today}T00:00:00",
            time_window_end=f"{today}T09:00:00",
        )

        summaries = {c.summary for c in candidates}
        assert "inside" in summaries
        assert "outside" not in summaries

    def test_filters_pushed_urls(self, tmp_path: Path):
        store = IngestionStore(root_dir=tmp_path)
        store.append_or_merge([_make_item(url="https://keep.com/1")])
        store.append_or_merge([_make_item(url="https://drop.com/1")])

        today = _today_str()
        candidates = store.load_window_candidates(
            time_window_start=f"{today}T00:00:00",
            time_window_end=f"{today}T23:59:59",
            pushed_urls={"https://drop.com/1"},
        )
        urls = {c.url for c in candidates}
        assert "https://keep.com/1" in urls
        assert "https://drop.com/1" not in urls

    def test_filters_pushed_keys(self, tmp_path: Path):
        store = IngestionStore(root_dir=tmp_path)
        store.append_or_merge([_make_item(url="https://keep.com/1")])
        store.append_or_merge([_make_item(url="https://drop.com/path")])

        today = _today_str()
        candidates = store.load_window_candidates(
            time_window_start=f"{today}T00:00:00",
            time_window_end=f"{today}T23:59:59",
            pushed_keys={"drop.com/path"},
        )
        keys = {c.canonical_key for c in candidates}
        assert "keep.com/1" in keys
        assert "drop.com/path" not in keys

    def test_empty_window_returns_empty(self, tmp_path: Path):
        store = IngestionStore(root_dir=tmp_path)
        store.append_or_merge([_make_item()])

        # 用完全不在范围内的窗口
        candidates = store.load_window_candidates(
            time_window_start="2020-01-01T00:00:00",
            time_window_end="2020-01-01T23:59:59",
        )
        assert candidates == []

    def test_skips_corrupted_jsonl_lines(self, tmp_path: Path):
        store = IngestionStore(root_dir=tmp_path)
        today = _today_str()
        day_dir = tmp_path / "data" / "ingestion" / today
        day_dir.mkdir(parents=True, exist_ok=True)

        # 手动写入混合内容
        (day_dir / "candidates.jsonl").write_text(
            '{"title":"OK","url":"https://ok.com/1","summary":"s","source":"t","category":"ai","canonical_key":"ok.com/1"}\n'
            'NOT JSON\n'
            '{"title":"OK2","url":"https://ok.com/2","summary":"s2","source":"t","category":"ai","canonical_key":"ok.com/2"}\n',
            encoding="utf-8",
        )

        candidates = store.load_window_candidates(
            time_window_start=f"{today}T00:00:00",
            time_window_end=f"{today}T23:59:59",
        )
        assert len(candidates) == 2

    def test_items_from_multiple_dirs_folded_together(self, tmp_path: Path):
        """跨目录同 key 条目也应按折叠规则合并。"""
        store = IngestionStore(root_dir=tmp_path)
        today = date.today()
        d1 = today.isoformat()
        d2 = (today - timedelta(days=1)).isoformat()

        ing = tmp_path / "data" / "ingestion"

        _write_jsonl(ing / d1, [_make_item(url="https://cross.com/a", summary="v1", fetched_at="2026-05-18T08:00:00")])
        _write_jsonl(ing / d2, [_make_item(url="https://cross.com/a", summary="v2 newer fetch", fetched_at="2026-05-18T09:00:00")])

        candidates = store.load_window_candidates(
            time_window_start=f"{d2}T00:00:00",
            time_window_end=f"{d1}T23:59:59",
        )
        assert len(candidates) == 1
        assert candidates[0].summary == "v2 newer fetch"


# ---------------------------------------------------------------------------
# prune_expired
# ---------------------------------------------------------------------------

class TestPruneExpired:
    def test_cleans_old_directories(self, tmp_path: Path):
        store = IngestionStore(root_dir=tmp_path)
        today = date.today()
        ing = tmp_path / "data" / "ingestion"

        # 创建多个日期的目录
        for days_ago in [0, 1, 2, 4, 7]:
            d = (today - timedelta(days=days_ago)).isoformat()
            _write_jsonl(ing / d, [_make_item(url=f"https://x.com/{days_ago}")])

        # keep_days=3 → 保留最近 3 天（today, -1, -2），删除更早的
        deleted = store.prune_expired(keep_days=3)
        assert deleted == 2  # -4 天和 -7 天应被删除

        remaining = sorted(d.name for d in ing.iterdir() if d.is_dir())
        expected = sorted(
            (today - timedelta(days=i)).isoformat() for i in range(3)
        )
        assert remaining == expected

    def test_returns_zero_when_no_expired(self, tmp_path: Path):
        store = IngestionStore(root_dir=tmp_path)
        today = date.today()
        ing = tmp_path / "data" / "ingestion"

        _write_jsonl(ing / today.isoformat(), [_make_item()])
        deleted = store.prune_expired(keep_days=7)
        assert deleted == 0

    def test_returns_zero_when_ingestion_dir_missing(self, tmp_path: Path):
        store = IngestionStore(root_dir=tmp_path)
        deleted = store.prune_expired(keep_days=3)
        assert deleted == 0

    def test_skips_non_date_directories(self, tmp_path: Path):
        """非 YYYY-MM-DD 格式的目录应被跳过，不报错也不删除。"""
        store = IngestionStore(root_dir=tmp_path)
        ing = tmp_path / "data" / "ingestion"
        (ing / "not-a-date").mkdir(parents=True, exist_ok=True)

        # 创建一个过期目录
        old = (date.today() - timedelta(days=10)).isoformat()
        _write_jsonl(ing / old, [_make_item()])

        deleted = store.prune_expired(keep_days=3)
        assert deleted == 1
        assert (ing / "not-a-date").is_dir()  # 未被删除
