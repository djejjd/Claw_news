"""只读历史回放 — 模拟推送流程，不写任何生产状态。"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path

from app.content.source_policy import build_source_policy_registry
from app.pipeline.selection import (
    reselect_digest_after_llm_relevance,
    select_digest,
    select_digest_with_topic_clustering,
)
from app.storage.ingestion_store import IngestionStore, filter_unexpired_candidates
from collectors.ai_rss import load_effective_feed_configuration
from infra.storage.state_store import StateStore


def _candidate_key(item) -> str:
    from app.pipeline.candidate import CandidateItem

    return item.canonical_key or CandidateItem.make_canonical_key(item.url or "")


def run_replay(
    data_dir: str,
    at: str,
    lookback_hours: int = 72,
    diversity_penalty_profile: str = "linear",
    topic_cluster_enabled: bool = False,
    topic_cluster_similarity_threshold: float = 0.7,
    topic_cluster_max_rounds: int = 10,
    llm_relevance_scores: dict[str, float] | None = None,
    llm_relevance_threshold: float = 0.5,
) -> dict:
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
    try:
        now = datetime.fromisoformat(at)
    except (ValueError, TypeError) as e:
        raise ValueError(f"非法时间参数 '{at}': {e}") from e

    data_path = Path(data_dir)
    if not data_path.exists():
        raise FileNotFoundError(f"数据目录不存在: {data_dir}")

    # 1. 加载 feeds.yaml 配置
    feeds_path = data_path.parent / "feeds.yaml"
    feed_config = load_effective_feed_configuration(feeds_path) or {}

    # 2. 构建 SourcePolicy registry
    feeds_raw = []
    for cat in ("ai", "tool", "game", "digital"):
        for f in feed_config.get("feeds", {}).get(cat, []):
            if isinstance(f, dict):
                feeds_raw.append({**f, "category": cat})
    for source, policy in feed_config.get("source_policies", {}).items():
        if isinstance(policy, dict):
            feeds_raw.append({**policy, "source": policy.get("source", source)})
    policies = build_source_policy_registry(feeds_raw)

    # 3. 复用生产读取路径：按 fetched_at 限窗、canonical_key 折叠和已发布项过滤。
    store = IngestionStore(root_dir=data_path.parent)
    state_store = StateStore(data_path)
    candidates = store.load_recent_candidates(
        now.isoformat(),
        lookback_hours=lookback_hours,
        pushed_urls=state_store.load_pushed_urls(),
        pushed_keys=state_store.load_published_keys(),
    )

    candidate_count = len(candidates)

    # 4. 按源有效期过滤
    candidates, expiry_rejected = filter_unexpired_candidates(candidates, now, policies)

    # 5. 综合来源内容级重分类，再执行相关性过滤
    from app.classifiers.content_category_classifier import (
        ContentCategoryClassifier,
        dynamic_sources_from_feed_config,
    )
    from app.classifiers.relevance_filter import build_relevance_filter

    ContentCategoryClassifier().classify_batch(
        candidates,
        dynamic_sources=dynamic_sources_from_feed_config(feed_config),
    )
    rf = build_relevance_filter(feed_config)
    candidates, relevance_rejected = rf.evaluate_batch(candidates, policies)

    rejection_reasons = Counter(r["reason"] for r in expiry_rejected + relevance_rejected)

    eligible_count = len(candidates)

    # 6. 三阶段选材
    from app.classifiers.topic_classifier import TopicClassifier

    TopicClassifier().classify_batch(candidates)
    baseline = select_digest(
        candidates,
        policies,
        now,
        "Asia/Shanghai",
        top_n=10,
        diversity_penalty_profile=diversity_penalty_profile,
    )
    result, cluster_events = select_digest_with_topic_clustering(
        candidates,
        policies,
        now,
        "Asia/Shanghai",
        top_n=10,
        diversity_penalty_profile=diversity_penalty_profile,
        enabled=topic_cluster_enabled,
        threshold=topic_cluster_similarity_threshold,
        max_rounds=topic_cluster_max_rounds,
    )
    llm_relevance_events: list[dict] = []
    if llm_relevance_scores is not None:
        from app.tools.llm import validate_relevance_scores

        initial_selected = result.selected
        candidates_by_key = {_candidate_key(item): item for item in candidates}
        initial_evidence_by_key = {evidence.canonical_key: evidence for evidence in result.evidence}

        def event_payload(event: str, item, evidence, selection_round: int, **extra) -> dict:
            return {
                "schema_version": 2,
                "event": event,
                "canonical_key": _candidate_key(item),
                "selection_round": selection_round,
                "final_score": evidence.final_score
                if evidence
                else getattr(item, "final_score", None),
                "selection_score": evidence.selection_score if evidence else None,
                "source": item.source,
                "category": item.category,
                "topic": item.topic,
                **extra,
            }

        scored_items = [
            {"url": item.url, "relevance": llm_relevance_scores.get(item.url)}
            for item in initial_selected
        ]
        scores = validate_relevance_scores(scored_items)
        rejected_keys = {
            _candidate_key(item)
            for item in initial_selected
            if scores[item.url] < llm_relevance_threshold
        }
        if rejected_keys:
            result, rerun_cluster_events, backfills = reselect_digest_after_llm_relevance(
                candidates,
                policies,
                now,
                excluded_canonical_keys=rejected_keys,
                initially_scored_keys={_candidate_key(item) for item in initial_selected},
                top_n=10,
                diversity_penalty_profile=diversity_penalty_profile,
                topic_cluster_enabled=topic_cluster_enabled,
                topic_cluster_threshold=topic_cluster_similarity_threshold,
                topic_cluster_max_rounds=topic_cluster_max_rounds,
            )
            final_evidence_by_key = {
                evidence.canonical_key: evidence for evidence in result.evidence
            }
            reselection_final_round = (
                max((event.selection_round for event in rerun_cluster_events), default=0) + 1
            )
            llm_relevance_events = (
                [
                    event_payload(
                        "temporary_selected",
                        item,
                        initial_evidence_by_key.get(_candidate_key(item)),
                        1,
                    )
                    for item in initial_selected
                ]
                + [
                    event_payload(
                        "llm_relevance_rejected",
                        item,
                        initial_evidence_by_key.get(_candidate_key(item)),
                        2,
                        relevance=scores[item.url],
                        threshold=llm_relevance_threshold,
                    )
                    for item in initial_selected
                    if _candidate_key(item) in rejected_keys
                ]
                + [
                    {
                        "schema_version": 2,
                        "event": "topic_cluster_excluded",
                        "canonical_key": event.loser_canonical_key,
                        "selection_round": event.selection_round,
                        "selection_stage": "llm_reselection",
                        "final_score": event.final_score,
                        "selection_score": event.selection_score,
                        "source": candidates_by_key[event.loser_canonical_key].source,
                        "category": candidates_by_key[event.loser_canonical_key].category,
                        "topic": candidates_by_key[event.loser_canonical_key].topic,
                        "component_winner_canonical_key": event.winner_canonical_key,
                        "trigger_edges": [
                            {
                                "left": left,
                                "right": right,
                                "title_similarity": title,
                                "url_similarity": url,
                            }
                            for left, right, title, url in event.trigger_edges
                        ],
                        "title_similarity": event.title_similarity,
                        "url_similarity": event.url_similarity,
                        "tokenizer_version": "nfkc-casefold-v1",
                    }
                    for event in rerun_cluster_events
                ]
                + [
                    event_payload(
                        "llm_relevance_backfill",
                        candidates_by_key[backfill["canonical_key"]],
                        final_evidence_by_key.get(backfill["canonical_key"]),
                        reselection_final_round,
                        relevance=None,
                        relevance_source="not_scored_backfill",
                    )
                    for backfill in backfills
                ]
                + [
                    event_payload(
                        "final_selected",
                        item,
                        final_evidence_by_key.get(_candidate_key(item)),
                        reselection_final_round + 1,
                        rendered=True,
                    )
                    for item in result.selected
                ]
            )

    # 7. 统计
    source_dist = dict(Counter(it.source for it in result.selected))
    cat_dist = dict(Counter(it.category for it in result.selected))
    cluster_rounds = [
        {
            "selection_round": round_trace.selection_round,
            "available_count": round_trace.available_count,
            "selected_before_count": round_trace.selected_before_count,
            "excluded_count": round_trace.excluded_count,
            "cumulative_excluded_count": round_trace.cumulative_excluded_count,
            "converged": round_trace.converged,
        }
        for round_trace in result.cluster_rounds
    ]
    if cluster_events:
        rejection_reasons["topic_cluster_similarity"] += len(cluster_events)

    today_count = 0
    backfill_count = 0
    for ev in result.evidence:
        if ev.phase in ("today_competition", "today_guarantee"):
            today_count += 1
        elif ev.phase == "historical_backfill":
            backfill_count += 1

    return {
        "candidate_count": candidate_count,
        "diversity_penalty_profile": diversity_penalty_profile,
        "topic_cluster_enabled": topic_cluster_enabled,
        "topic_cluster_before_count": len(baseline.selected),
        "topic_cluster_excluded_count": len(cluster_events),
        "topic_cluster_rounds": cluster_rounds,
        "topic_cluster_calibration": {
            "status": "pending_real_annotations",
            "followup": "CG-P3-02-FOLLOWUP-01",
        },
        "topic_cluster_events": [
            {
                "selection_round": event.selection_round,
                "winner_canonical_key": event.winner_canonical_key,
                "loser_canonical_key": event.loser_canonical_key,
                "title_similarity": event.title_similarity,
                "url_similarity": event.url_similarity,
            }
            for event in cluster_events
        ],
        "llm_relevance_events": llm_relevance_events,
        "eligible_count": eligible_count,
        "selected_count": len(result.selected),
        "source_distribution": source_dist,
        "category_distribution": cat_dist,
        "today_count": today_count,
        "backfill_count": backfill_count,
        "rejection_reasons": dict(rejection_reasons),
        "soft_source_cap_exceeded_count": sum(
            evidence.soft_source_cap_exceeded for evidence in result.evidence
        ),
        "selection_evidence": [
            {
                "canonical_key": evidence.canonical_key,
                "phase": evidence.phase,
                "final_score": evidence.final_score,
                "diversity_penalty": evidence.diversity_penalty,
                "selection_score": evidence.selection_score,
                "soft_source_cap_exceeded": evidence.soft_source_cap_exceeded,
            }
            for evidence in result.evidence
        ],
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
