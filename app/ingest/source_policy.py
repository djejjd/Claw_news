from __future__ import annotations

from typing import Any

from app.pipeline.candidate import CandidateItem

_MIN_SUMMARY_LENGTH = 5
_MIN_RUNS_FOR_ADJUSTMENT = 12
_ADJUST_STEP = 2
_COOLDOWN_ROUNDS = 6


def should_accept_candidate(item: CandidateItem) -> bool:
    """Apply the basic admission rules for ingest candidates."""
    if not item.title.strip():
        return False
    if not item.url.strip():
        return False
    if item.category.strip().lower() != "ai":
        return False
    if len((item.summary or "").strip()) < _MIN_SUMMARY_LENGTH:
        return False
    return True


def update_fetch_count_from_metrics(state: dict, metrics: dict, now_iso: str) -> dict:
    """Adjust fetch_count with conservative rate-based rules and cooldown."""
    updated = dict(state)
    fetch_count = _coerce_int(updated.get("fetch_count", 0))
    min_fetch_count = _coerce_int(updated.get("min_fetch_count", fetch_count))
    max_fetch_count = _coerce_int(updated.get("max_fetch_count", fetch_count))
    clamped_fetch_count = _clamp(fetch_count, min_fetch_count, max_fetch_count)
    updated["fetch_count"] = clamped_fetch_count

    cooldown_remaining = _coerce_int(updated.get("cooldown_remaining", 0))
    if cooldown_remaining > 0:
        updated["cooldown_remaining"] = max(cooldown_remaining - 1, 0)
        return updated

    runs = _coerce_int(metrics.get("runs", 0))
    if runs < _MIN_RUNS_FOR_ADJUSTMENT:
        return updated

    effective_new_rate = _coerce_float(metrics.get("effective_new_rate", 0.0))
    selection_rate = _coerce_float(metrics.get("selection_rate", 0.0))

    delta = 0
    if effective_new_rate >= 0.5 and selection_rate >= 0.2:
        delta = _ADJUST_STEP
    elif effective_new_rate <= 0.1:
        delta = -_ADJUST_STEP

    if delta == 0:
        return updated

    next_fetch_count = _clamp(clamped_fetch_count + delta, min_fetch_count, max_fetch_count)
    if next_fetch_count == clamped_fetch_count:
        return updated

    updated["fetch_count"] = next_fetch_count
    updated["cooldown_remaining"] = _COOLDOWN_ROUNDS
    updated["last_adjusted_at"] = now_iso
    return updated


def _coerce_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _coerce_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _clamp(value: int, lower: int, upper: int) -> int:
    if value < lower:
        return lower
    if value > upper:
        return upper
    return value
