"""
Topic Classifier — rule-based light classification for CandidateItem.

6 topic buckets with pure keyword matching, no LLM calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.pipeline.candidate import CandidateItem

# ---------------------------------------------------------------------------
# Match result helper
# ---------------------------------------------------------------------------


@dataclass
class _MatchResult:
    """Internal result of a rule match attempt."""

    topic: str
    source_hit: bool = False
    title_hit_count: int = 0
    summary_hit_count: int = 0


# ---------------------------------------------------------------------------
# TopicClassifier
# ---------------------------------------------------------------------------


class TopicClassifier:
    """Rule-based topic classifier.

    Matches CandidateItem against 6 topic buckets in priority order using
    keyword matching on title, summary, source, and category.  No LLM calls.
    """

    # Topic rule definitions in priority order (first match wins).
    _RULES: List[Dict[str, Any]] = [
        {
            "topic": "model_release",
            "weight": 3.0,
            "source_check": "huggingface",
            # Condition A: source == huggingface AND title contains any of these
            "title_keywords": [
                "model",
                "llm",
                "gpt",
                "claude",
                "gemini",
                "release",
                "发布",
                "开源",
                "weights",
                "checkpoint",
                "大模型",
                "新模型",
            ],
            # Condition B: title has any of these AND summary has any of:
            "and_title_keywords": ["大模型", "新模型", "发布", "开源"],
            "and_summary_keywords": ["参数", "训练", "架构"],
        },
        {
            "topic": "agent_workflow",
            "weight": 2.5,
            "title_keywords": [
                "agent",
                "智能体",
                "助手",
                "工作流",
                "workflow",
                "tool use",
                "function call",
                "rag",
                "多步推理",
                "自主",
                "autonomous",
            ],
        },
        {
            "topic": "developer_tooling",
            "weight": 2.0,
            "title_keywords": [
                "ide",
                "copilot",
                "代码",
                "编程",
                "debug",
                "调试",
                "github",
                "cursor",
                "v0",
                "bolt",
                "replit",
                "template",
                "tool",
                "工具链",
                "sdk",
                "api",
                "framework",
                "库",
            ],
        },
        {
            "topic": "research_benchmark",
            "weight": 2.0,
            "title_keywords": [
                "benchmark",
                "评测",
                "排行榜",
                "超越",
                "击败",
                "sota",
                "state-of-the-art",
                "准确率",
                "论文",
                "研究",
                "arc",
                "mmlu",
                "humaneval",
                "swe-bench",
            ],
        },
        {
            "topic": "infrastructure",
            "weight": 1.5,
            "title_keywords": [
                "gpu",
                "h100",
                "a100",
                "算力",
                "集群",
                "推理",
                "部署",
                "微调",
                "finetune",
                "lora",
                "量化",
                "quantization",
                "训练",
                "分布式",
                "latency",
                "延迟",
            ],
            "summary_keywords": [
                "gpu",
                "h100",
                "a100",
                "算力",
                "集群",
                "推理",
                "部署",
                "微调",
                "finetune",
                "lora",
                "量化",
                "quantization",
                "训练",
                "分布式",
                "latency",
                "延迟",
            ],
        },
        {
            "topic": "application_case",
            "weight": 1.0,
            "category_check": "ai",
            "title_keywords": [
                "应用",
                "落地",
                "产品",
                "融资",
                "收购",
                "合作",
                "demo",
                "案例",
            ],
        },
    ]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify(self, item: CandidateItem) -> CandidateItem:
        """Classify a single CandidateItem in-place, returning it."""
        title_lower = item.title.lower()
        summary_lower = (item.summary or "").lower()

        for rule in self._RULES:
            result = self._try_match(rule, item, title_lower, summary_lower)
            if result is not None:
                item.topic = result.topic
                item.topic_confidence = self._calc_confidence(
                    result.source_hit,
                    result.title_hit_count,
                    result.summary_hit_count,
                )
                return item

        # Nothing matched — unconditional fallback
        item.topic = "application_case"
        item.topic_confidence = 0.1
        return item

    def classify_batch(self, items: List[CandidateItem]) -> List[CandidateItem]:
        """Classify a batch of CandidateItems in-place, returning them."""
        for item in items:
            self.classify(item)
        return items

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _try_match(
        self,
        rule: Dict[str, Any],
        item: CandidateItem,
        title_lower: str,
        summary_lower: str,
    ) -> Optional[_MatchResult]:
        """Attempt to match *item* against *rule*.  Returns _MatchResult or None."""
        topic = rule["topic"]
        title_kws: List[str] = rule.get("title_keywords", [])
        summary_kws: List[str] = rule.get("summary_keywords", [])
        source_check: Optional[str] = rule.get("source_check")
        category_check: Optional[str] = rule.get("category_check")

        # ---- source / category hit ----
        source_hit = False
        if source_check is not None and item.source.lower() == source_check:
            source_hit = True
        if category_check is not None and item.category == category_check:
            source_hit = True

        # ---- special case: model_release has two sub-conditions ----
        if topic == "model_release":
            return self._match_model_release(
                item, title_lower, summary_lower, source_hit, rule
            )

        # ---- generic: any title, summary, or source hit ----
        title_hit_count = sum(1 for kw in title_kws if kw in title_lower)
        summary_hit_count = sum(1 for kw in summary_kws if kw in summary_lower)

        if title_hit_count > 0 or summary_hit_count > 0 or source_hit:
            return _MatchResult(
                topic=topic,
                source_hit=source_hit,
                title_hit_count=title_hit_count,
                summary_hit_count=summary_hit_count,
            )

        return None

    def _match_model_release(
        self,
        item: CandidateItem,  # noqa: ARG002  (kept for symmetry)
        title_lower: str,
        summary_lower: str,
        source_hit: bool,
        rule: Dict[str, Any],
    ) -> Optional[_MatchResult]:
        title_kws: List[str] = rule["title_keywords"]
        and_title_kws: List[str] = rule["and_title_keywords"]
        and_summary_kws: List[str] = rule["and_summary_keywords"]

        # Condition A: source == huggingface AND title keyword present
        cond_a = source_hit and any(kw in title_lower for kw in title_kws)

        # Condition B: title AND summary keyword present
        cond_b_title = any(kw in title_lower for kw in and_title_kws)
        cond_b_summary = any(kw in summary_lower for kw in and_summary_kws)
        cond_b = cond_b_title and cond_b_summary

        if cond_a or cond_b:
            title_hit_count = sum(1 for kw in title_kws if kw in title_lower)
            # Count summary hits from condition B keywords only when cond_b is true
            summary_hit_count = (
                sum(1 for kw in and_summary_kws if kw in summary_lower)
                if cond_b
                else 0
            )
            return _MatchResult(
                topic="model_release",
                source_hit=source_hit,
                title_hit_count=title_hit_count,
                summary_hit_count=summary_hit_count,
            )

        return None

    @staticmethod
    def _calc_confidence(
        source_hit: bool,
        title_count: int,
        summary_count: int,
    ) -> float:
        """Calculate topic_confidence from match signals.

        Cascading tiers (first satisfied wins):
        - source + title hits >= 2  → 0.9
        - title hits >= 1          → 0.7
        - summary hits >= 1        → 0.5
        - source hit only          → 0.3
        - nothing                  → 0.1  (handled by caller)
        """
        if source_hit + title_count >= 2:
            return 0.9
        if title_count >= 1:
            return 0.7
        if summary_count >= 1:
            return 0.5
        if source_hit:
            return 0.3
        return 0.1
