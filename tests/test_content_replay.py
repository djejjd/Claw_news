"""Task 7: content_replay 测试 — 只读验证 + 回放分布。"""

import hashlib
import json
from pathlib import Path

import pytest

from app.pipeline.candidate import CandidateItem

_FIXED_AT = "2026-07-11T09:00:00+08:00"


def _snapshot_hashes(root: Path) -> dict[str, str]:
    """递归计算目录下所有文件的 SHA-256。"""
    if not root.exists():
        return {}
    hashes = {}
    for entry in sorted(root.rglob("*")):
        if entry.is_file():
            hashes[str(entry.relative_to(root))] = hashlib.sha256(entry.read_bytes()).hexdigest()
    return hashes


def _seed_replay_fixture(tmp_path: Path) -> Path:
    """创建最小回放 fixture：候选 + 配置。"""
    data_dir = tmp_path / "data"
    ing_dir = data_dir / "ingestion" / "2026-07-11"
    ing_dir.mkdir(parents=True)

    items = [
        CandidateItem(
            title="AI 今日",
            url="https://ai1.test",
            summary="AI news",
            source="qbitai",
            category="ai",
            published_at="2026-07-11T08:00:00+08:00",
            canonical_key="ai1",
            fetched_at="2026-07-11T08:00:00+08:00",
        ),
        CandidateItem(
            title="工具 今日",
            url="https://t1.test",
            summary="tool news",
            source="sspai",
            category="tool",
            published_at="2026-07-11T08:00:00+08:00",
            canonical_key="t1",
            fetched_at="2026-07-11T08:00:00+08:00",
        ),
        CandidateItem(
            title="游戏 今日",
            url="https://g1.test",
            summary="game news",
            source="yystv",
            category="game",
            published_at="2026-07-11T08:00:00+08:00",
            canonical_key="g1",
            fetched_at="2026-07-11T08:00:00+08:00",
        ),
    ]
    # Write candidates
    cand_path = ing_dir / "candidates.jsonl"
    with open(cand_path, "w", encoding="utf-8") as f:
        for item in items:
            from dataclasses import asdict

            f.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")

    # Write index
    idx_path = ing_dir / "index.json"
    idx_path.write_text(json.dumps({"date": "2026-07-11", "seen_keys": [], "item_count": 3}))

    # Create feeds.yaml-like config for policies
    feeds_path = tmp_path / "feeds.yaml"
    import yaml

    feeds_path.write_text(
        yaml.dump(
            {
                "feeds": {
                    "ai": [
                        {
                            "url": "https://qbitai.com/feed",
                            "source": "qbitai",
                            "tier": "vertical",
                            "retention_hours": 48,
                            "quality_weight": 3.5,
                            "filter_profile": "standard",
                        }
                    ],
                    "tool": [
                        {
                            "url": "https://sspai.com/feed",
                            "source": "sspai",
                            "tier": "vertical",
                            "retention_hours": 48,
                            "quality_weight": 3.5,
                            "filter_profile": "standard",
                        }
                    ],
                    "game": [
                        {
                            "url": "https://yystv.cn/rss/feed",
                            "source": "yystv",
                            "tier": "vertical",
                            "retention_hours": 48,
                            "quality_weight": 3.5,
                            "filter_profile": "standard",
                        }
                    ],
                }
            }
        )
    )

    return data_dir


def _seed_fixture_with_history(tmp_path: Path) -> Path:
    """创建含历史候选的回放 fixture。"""
    data_dir = tmp_path / "data"

    # 今日候选
    ing_today = data_dir / "ingestion" / "2026-07-11"
    ing_today.mkdir(parents=True)
    today_items = [
        CandidateItem(
            title=f"AI today {i}",
            url=f"https://ai-t{i}.test",
            summary="AI",
            source="qbitai",
            category="ai",
            published_at="2026-07-11T08:00:00+08:00",
            canonical_key=f"ai-t{i}",
            fetched_at="2026-07-11T08:00:00+08:00",
        )
        for i in range(2)
    ]
    from dataclasses import asdict

    with open(ing_today / "candidates.jsonl", "w") as f:
        for item in today_items:
            f.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")
    idx = json.dumps({"date": "2026-07-11", "seen_keys": [], "item_count": 2})
    (ing_today / "index.json").write_text(idx)

    # 昨日候选（用于 cross-day backfill）
    ing_yesterday = data_dir / "ingestion" / "2026-07-10"
    ing_yesterday.mkdir(parents=True)
    yesterday_items = [
        CandidateItem(
            title=f"AI yesterday {i}",
            url=f"https://ai-y{i}.test",
            summary="AI",
            source="qbitai",
            category="ai",
            published_at="2026-07-10T08:00:00+08:00",
            canonical_key=f"ai-y{i}",
            fetched_at="2026-07-10T08:00:00+08:00",
        )
        for i in range(3)
    ]
    with open(ing_yesterday / "candidates.jsonl", "w") as f:
        for item in yesterday_items:
            f.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")
    idx2 = json.dumps({"date": "2026-07-10", "seen_keys": [], "item_count": 3})
    (ing_yesterday / "index.json").write_text(idx2)

    # feeds.yaml
    import yaml

    feeds_path = tmp_path / "feeds.yaml"
    feeds_path.write_text(
        yaml.dump(
            {
                "feeds": {
                    "ai": [
                        {
                            "url": "https://qbitai.com/feed",
                            "source": "qbitai",
                            "tier": "vertical",
                            "retention_hours": 48,
                            "quality_weight": 3.5,
                            "filter_profile": "standard",
                        }
                    ],
                }
            }
        )
    )

    return data_dir


# ---- 测试 ----


def test_module_importable():
    """模块可导入。"""
    from app.tools.content_replay import run_replay  # noqa: F401


def test_replay_is_read_only(tmp_path, monkeypatch):
    """运行前后所有生产状态文件 hash 不变。"""
    from app.tools.content_replay import run_replay

    _seed_replay_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)

    data_path = tmp_path / "data"
    before = _snapshot_hashes(data_path)
    result = run_replay(data_dir="data", at=_FIXED_AT)
    after = _snapshot_hashes(data_path)

    assert result["selected_count"] >= 0
    assert before == after  # no files modified


def test_replay_reports_distribution(tmp_path, monkeypatch):
    """输出包含来源分布和分类分布。"""
    from app.tools.content_replay import run_replay

    _seed_replay_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = run_replay(data_dir="data", at=_FIXED_AT)
    assert result["candidate_count"] >= 0
    assert "selected_count" in result
    assert "source_distribution" in result
    assert "category_distribution" in result


def test_replay_historical_backfill(tmp_path, monkeypatch):
    """历史候选用于补足分类不足。"""
    from app.tools.content_replay import run_replay

    _seed_fixture_with_history(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = run_replay(data_dir="data", at=_FIXED_AT)
    # 今日只有 2 条 AI，AI 最低需要 3，从昨日补 1 条
    assert result["backfill_count"] >= 1


def test_replay_invalid_at_fails():
    """非法时间参数应明确失败。"""
    from app.tools.content_replay import run_replay

    with pytest.raises(ValueError):
        run_replay(data_dir="data", at="not-a-time")


def test_replay_missing_data_dir(tmp_path, monkeypatch):
    """数据目录不存在时明确失败。"""
    from app.tools.content_replay import run_replay

    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError):
        run_replay(data_dir="nonexistent", at=_FIXED_AT)
