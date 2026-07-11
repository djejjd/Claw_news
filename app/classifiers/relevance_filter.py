"""跨分类相关性过滤 — 纯规则、无网络、可解释。

按 AI / 工具 / 游戏三类独立维护正向词和排除词。
三档 profile 只改变复核阈值，不绕过排除规则。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app.content.source_policy import SourcePolicy
from app.pipeline.candidate import CandidateItem

# ---- 默认规则 ----

_DEFAULT_RULES: dict[str, dict[str, list[str]]] = {
    "ai": {
        "positive": [
            "ai", "大模型", "gpt", "llm", "agent", "智能体",
            "训练", "推理", "开源", "模型", "深度学习", "机器学习",
            "神经网络", "transformer", "扩散", "多模态", "embedd",
            "fine-tun", "预训练", "对齐", "rlhf", "benchmark",
            "评测", "论文", "研究", "发布", "api", "token",
            "算力", "gpu", "集群", "部署",
        ],
        "negative": [],
    },
    "tool": {
        "positive": [
            "工具", "app", "软件", "硬件", "效率", "插件", "扩展",
            "开发", "编程", "代码", "开源项目", "框架", "库",
            "sdk", "api", "ide", "编辑器", "终端", "命令行",
            "自动化", "脚本", "部署", "运维", "监控", "安全",
            "芯片", "处理器", "手机", "笔记本", "系统更新",
        ],
        "negative": [
            "汽车促销", "限时促销", "大降价", "清仓",
            "运营商套餐", "话费", "流量包", "宽带优惠",
            "电影票房", "暑期档", "国庆档", "热播剧", "综艺",
            "家电降价", "空调促销", "冰箱洗衣机",
            "天气", "气温", "降雨", "台风",
            "股票", "基金", "期货", "理财",
        ],
    },
    "game": {
        "positive": [
            "游戏", "主机", "steam", "switch", "ps5", "xbox",
            "手游", "上线", "赛季", "联动", "版本更新",
            "新游", "评测", "发售", "dlc", "资料片",
            "独立游戏", "3a", "电竞", "比赛", "战队",
            "玩法", "剧情", "画面", "引擎",
        ],
        "negative": [],
    },
}

# profile 门槛
_PROFILE_THRESHOLDS = {"strict": 0.7, "standard": 0.5, "lenient": 0.3}

# ---- 数据类 ----


@dataclass(frozen=True)
class RelevanceResult:
    accepted: bool
    confidence: float
    reason: str  # negative_rule | positive_rule | rule_conflict | below_threshold | classifier_pass
    matched_positive: tuple[str, ...] = ()
    matched_negative: tuple[str, ...] = ()


# ---- RelevanceFilter ----


class RelevanceFilter:
    """纯规则相关性过滤器。"""

    def __init__(self, rules: dict[str, dict[str, list[str]]] | None = None):
        self._rules = rules or _DEFAULT_RULES

    # ---- Public ----

    def evaluate(self, item: CandidateItem, policy: SourcePolicy) -> RelevanceResult:
        """判断单篇候选是否通过相关性过滤。"""
        cat_rules = self._rules.get(item.category, {})
        pos_words = cat_rules.get("positive", [])
        neg_words = cat_rules.get("negative", [])

        text = f"{item.title} {item.summary or ''}".lower()

        # 1. 检查排除词（跨类检查，防止 IT之家汽车促销被误标为 AI）
        all_neg_words: set[str] = set(neg_words)
        for other_rules in self._rules.values():
            all_neg_words.update(other_rules.get("negative", []))
        matched_neg = tuple(w for w in all_neg_words if w in text)

        # 2. 检查正向词
        matched_pos = tuple(w for w in pos_words if w in text)

        # 3. 正负冲突 → 拒绝
        if matched_neg and matched_pos:
            return RelevanceResult(
                accepted=False, confidence=0.0, reason="rule_conflict",
                matched_positive=matched_pos, matched_negative=matched_neg,
            )

        # 4. 排除词命中 → 拒绝
        if matched_neg:
            return RelevanceResult(
                accepted=False, confidence=0.0, reason="negative_rule",
                matched_negative=matched_neg,
            )

        # 5. 正向词命中 → 接受
        if matched_pos:
            confidence = 0.9 if len(matched_pos) >= 2 else 0.7
            return RelevanceResult(
                accepted=True, confidence=confidence, reason="positive_rule",
                matched_positive=matched_pos,
            )

        # 6. 都没命中 → 用 TopicClassifier 复核
        confidence = self._classifier_confidence(item)
        threshold = _PROFILE_THRESHOLDS.get(policy.filter_profile, 0.5)
        if confidence >= threshold:
            return RelevanceResult(
                accepted=True, confidence=confidence, reason="classifier_pass",
            )
        return RelevanceResult(
            accepted=False, confidence=confidence, reason="below_threshold",
        )

    def evaluate_batch(
        self, items: list[CandidateItem], policies: dict[str, SourcePolicy],
    ) -> tuple[list[CandidateItem], list[dict]]:
        """批量评估，返回 (保留列表, 拒绝审计)。"""
        kept: list[CandidateItem] = []
        rejected: list[dict] = []
        for item in items:
            policy = policies.get(item.source)
            if policy is None:
                policy = SourcePolicy(source=item.source)
            result = self.evaluate(item, policy)
            if result.accepted:
                kept.append(item)
            else:
                ck = item.canonical_key or CandidateItem.make_canonical_key(
                    item.url or "")
                rejected.append({
                    "canonical_key": ck,
                    "source": item.source,
                    "category": item.category,
                    "reason": result.reason,
                    "confidence": result.confidence,
                    "matched_positive": list(result.matched_positive),
                    "matched_negative": list(result.matched_negative),
                })
        return kept, rejected

    # ---- Internal ----

    def _classifier_confidence(self, item: CandidateItem) -> float:
        """获取跨分类置信度，不污染 item.topic。

        tool/game 用正向词命中数做轻量判断（TopicClassifier 只面向 AI）。
        置信度映射：0.9 / 0.7 / 0.5 / 0.3 / 0.1
        """
        # TopicClassifier 只面向 AI，对 tool/game 不适用
        if item.category in ("tool", "game"):
            cat_rules = self._rules.get(item.category, {})
            pos_words = cat_rules.get("positive", [])
            text = f"{item.title} {item.summary or ''}".lower()
            pos_hits = sum(1 for w in pos_words if w in text)
            return 0.5 if pos_hits else 0.1

        from app.classifiers.topic_classifier import TopicClassifier

        tc = TopicClassifier()
        tc.classify(item)
        tc_conf = item.topic_confidence or 0.0
        return tc_conf if tc_conf > 0 else 0.1


# ---- 工厂 ----

def build_relevance_filter(config: Mapping[str, Any] | None = None) -> RelevanceFilter:
    """从已加载配置构建 RelevanceFilter。

    config 应包含可选的 relevance_rules 映射；缺少或非法时使用默认规则。
    不读取 YAML、不访问网络。
    """
    if config is None:
        return RelevanceFilter()
    try:
        raw_rules = config.get("relevance_rules")
        if isinstance(raw_rules, dict) and raw_rules:
            return RelevanceFilter(rules=raw_rules)
    except (TypeError, KeyError):
        import logging
        logging.getLogger(__name__).warning(
            "relevance_rules 配置解析失败，使用默认规则"
        )
    return RelevanceFilter()
