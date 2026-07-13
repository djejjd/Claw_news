"""只读历史回放 — 模拟推送流程，不写任何生产状态。"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from app.content.source_policy import build_source_policy_registry
from app.pipeline.candidate import CandidateItem
from app.pipeline.selection import select_digest
from app.storage.ingestion_store import filter_unexpired_candidates


def run_replay(data_dir: str, at: str, lookback_hours: int = 72) -> dict:
    """只读回放：读取历史候选，模拟过期过滤→相关性→选材，返回分布统计。

    Args:
        data_dir: 数据目录路径 (包含 ingestion/ 子目录)
        at: ISO 时间字符串，如 "2026-07-11T09:00:00+08:00"
        lookback_hours: 回看小时数

    Returns:
        dict with: candidate_count, eligible_count, selected_count,
                   source_distribution, category_distribution, today_count,
                   backfill_count, rejection_reasons, selected

    Raises:
        ValueError: at 参数格式非法
        FileNotFoundError: data_dir 不存在
    """
    data_path = Path(data_dir)
    if not data_path.exists():
        raise FileNotFoundError(f"数据目录不存在: {data_dir}")

    try:
        now = datetime.fromisoformat(at)
    except (ValueError, TypeError) as e:
        raise ValueError(f"非法时间参数 '{at}': {e}") from e

    # 1. 加载 feeds.yaml 配置
    feeds_path = data_path.parent / "feeds.yaml"
    feed_config = {}
    if feeds_path.exists():
        import yaml
        feed_config = yaml.safe_load(feeds_path.read_text(encoding="utf-8")) or {}

    # 2. 构建 SourcePolicy registry
    feeds_raw = []
    for cat in ("ai", "tool", "game"):
        for f in feed_config.get("feeds", {}).get(cat, []):
            if isinstance(f, dict):
                feeds_raw.append({**f, "category": cat})
    policies = build_source_policy_registry(feeds_raw)

    # 3. 读取 72 小时内候选
    start_dt = now - timedelta(hours=lookback_hours)
    candidates: list[CandidateItem] = []
    ingestion_dir = data_path / "ingestion"
    if ingestion_dir.exists():
        for day_dir in sorted(ingestion_dir.iterdir()):
            if not day_dir.is_dir():
                continue
            try:
                dir_date = datetime.strptime(day_dir.name, "%Y-%m-%d").date()
            except ValueError:
                continue
            if not (start_dt.date() <= dir_date <= now.date()):
                continue
            cand_path = day_dir / "candidates.jsonl"
            if not cand_path.exists():
                continue
            for line in cand_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    candidates.append(CandidateItem(**{
                        k: v for k, v in data.items()
                        if k in _CANDIDATE_FIELDS
                    }))
                except (json.JSONDecodeError, TypeError):
                    continue

    candidate_count = len(candidates)

    # 4. 按源有效期过滤
    candidates, expiry_rejected = filter_unexpired_candidates(candidates, now, policies)

    # 5. 相关性过滤
    from app.classifiers.relevance_filter import build_relevance_filter
    rf = build_relevance_filter(feed_config)
    candidates, relevance_rejected = rf.evaluate_batch(candidates, policies)

    rejection_reasons = Counter(r["reason"] for r in expiry_rejected + relevance_rejected)

    eligible_count = len(candidates)

    # 6. 三阶段选材
    from app.classifiers.topic_classifier import TopicClassifier
    TopicClassifier().classify_batch(candidates)
    result = select_digest(candidates, policies, now, "Asia/Shanghai", top_n=10)

    # 7. 统计
    source_dist = dict(Counter(it.source for it in result.selected))
    cat_dist = dict(Counter(it.category for it in result.selected))

    today_count = 0
    backfill_count = 0
    for it, ev in zip(result.selected, result.evidence):
        if ev.phase == "today_competition" or ev.phase == "today_guarantee":
            today_count += 1
        elif ev.phase == "historical_backfill":
            backfill_count += 1

    return {
        "candidate_count": candidate_count,
        "eligible_count": eligible_count,
        "selected_count": len(result.selected),
        "source_distribution": source_dist,
        "category_distribution": cat_dist,
        "today_count": today_count,
        "backfill_count": backfill_count,
        "rejection_reasons": dict(rejection_reasons),
        "selected": [
            {
                "title": it.title,
                "source": it.source,
                "category": it.category,
                "url": it.url,
            }
            for it in result.selected
        ],
    }


_CANDIDATE_FIELDS = {
    f.name for f in CandidateItem.__dataclass_fields__.values()  # type: ignore[attr-defined]
}
