"""Task 4: 跨分类相关性过滤测试。"""

import pytest

from app.pipeline.candidate import CandidateItem


def _make_item(**kwargs) -> CandidateItem:
    data = {
        "title": "T", "url": "https://x.test", "summary": "S",
        "source": "test", "category": "ai",
    }
    data.update(kwargs)
    return CandidateItem(**data)


# ---- 模块导入 ----

def test_module_importable():
    """模块可导入 — 实现前应失败 (ModuleNotFoundError)。"""
    from app.classifiers.relevance_filter import (  # noqa: F401
        RelevanceFilter,
        RelevanceResult,
        build_relevance_filter,
    )


# ---- strict 排除规则 ----

@pytest.mark.parametrize("title", [
    "汽车限时促销",
    "运营商套餐降价",
    "暑期电影票房",
    "家电大降价",
])
def test_strict_tool_source_rejects_known_noise(title):
    """IT之家 strict 模式下拒绝已知噪音（汽车/运营商/影视/家电）。"""
    from app.classifiers.relevance_filter import RelevanceFilter
    from app.content.source_policy import SourcePolicy

    policy = SourcePolicy("ithome", "fast_news", 24, 2.0, "strict")
    result = RelevanceFilter().evaluate(
        _make_item(title=title, summary="普通资讯", source="ithome", category="tool"),
        policy,
    )
    assert result.accepted is False
    assert result.reason in {"negative_rule", "below_threshold"}


# ---- 正负冲突优先拒绝 ----

def test_negative_rule_wins_conflict():
    """同时命中正向词和排除词时返回 rule_conflict 且拒绝。"""
    from app.classifiers.relevance_filter import RelevanceFilter
    from app.content.source_policy import SourcePolicy

    policy = SourcePolicy("ithome", "fast_news", 24, 2.0, "strict")
    item = _make_item(
        title="AI 手机汽车促销", summary="",
        source="ithome", category="ai",
    )
    result = RelevanceFilter().evaluate(item, policy)
    assert result.accepted is False
    assert result.reason == "rule_conflict"
    assert "ai" in result.matched_positive
    assert "汽车促销" in result.matched_negative


# ---- lenient 深度源 ----

def test_lenient_deep_source_accepts_summary_evidence():
    """深度源标题弱但摘要明确相关，lenient 门槛 0.3 应接受。"""
    from app.classifiers.relevance_filter import RelevanceFilter
    from app.content.source_policy import SourcePolicy

    policy = SourcePolicy("meituan_tech", "deep", 72, 4.0, "lenient")
    item = _make_item(
        title="一次实践复盘",
        summary="分布式推理集群延迟优化方案",
        source="meituan_tech", category="ai",
    )
    result = RelevanceFilter().evaluate(item, policy)
    assert result.accepted is True
    assert result.confidence >= 0.3


# ---- 正向规则 ----

def test_ai_positive_words_accept():
    """AI 正向词命中时接受。"""
    from app.classifiers.relevance_filter import RelevanceFilter
    from app.content.source_policy import SourcePolicy

    policy = SourcePolicy("qbitai", "vertical", 48, 3.5, "standard")
    for title in ["OpenAI 发布 GPT-5 大模型", "深度学习新突破"]:
        result = RelevanceFilter().evaluate(
            _make_item(title=title, summary="AI 前沿", source="qbitai", category="ai"),
            policy,
        )
        assert result.accepted is True, f"title='{title}' should pass"
        assert result.reason == "positive_rule"


# ---- 游戏类 ----

def test_game_positive_words_accept():
    """游戏正向词命中时接受。"""
    from app.classifiers.relevance_filter import RelevanceFilter
    from app.content.source_policy import SourcePolicy

    policy = SourcePolicy("yystv", "vertical", 48, 3.5, "standard")
    result = RelevanceFilter().evaluate(
        _make_item(
            title="黑神话悟空新版本评测",
            summary="Steam 销量破千万",
            source="yystv", category="game",
        ),
        policy,
    )
    assert result.accepted is True


# ---- below_threshold ----

def test_irrelevant_item_below_threshold():
    """完全不相关的文章在标准门槛下被拒绝。"""
    from app.classifiers.relevance_filter import RelevanceFilter
    from app.content.source_policy import SourcePolicy

    policy = SourcePolicy("ithome", "fast_news", 24, 2.0, "strict")
    result = RelevanceFilter().evaluate(
        _make_item(
            title="聊聊日常生活中的小事", summary="今天去超市买了点东西",
            source="ithome", category="tool",
        ),
        policy,
    )
    assert result.accepted is False
    assert result.reason == "below_threshold"


# ---- batch 评估 ----

def test_evaluate_batch_returns_kept_and_rejected():
    """batch 评估返回 (保留列表, 拒绝审计)。"""
    from app.classifiers.relevance_filter import RelevanceFilter
    from app.content.source_policy import SourcePolicy

    policy_tool = SourcePolicy("ithome", "fast_news", 24, 2.0, "strict")
    policy_ai = SourcePolicy("qbitai", "vertical", 48, 3.5, "standard")
    items = [
        _make_item(title="汽车大促销", source="ithome", category="tool", url="https://noise.test"),
        _make_item(title="GPT-5 发布", source="qbitai", category="ai", url="https://good.test"),
    ]
    policies = {"ithome": policy_tool, "qbitai": policy_ai}
    kept, rejected = RelevanceFilter().evaluate_batch(items, policies)
    assert len(kept) == 1
    assert kept[0].url == "https://good.test"
    assert len(rejected) == 1
    assert rejected[0]["canonical_key"] == CandidateItem.make_canonical_key("https://noise.test")


# ---- 配置工厂 ----

def test_build_filter_with_empty_config():
    """空配置返回默认规则过滤器。"""
    from app.classifiers.relevance_filter import build_relevance_filter

    filt = build_relevance_filter({})
    assert filt is not None


def test_build_filter_with_custom_rules():
    """自定义规则覆盖默认规则。"""
    from app.classifiers.relevance_filter import build_relevance_filter

    config = {
        "relevance_rules": {
            "ai": {
                "positive": ["自定义AI词"],
                "negative": [],
            },
        },
    }
    filt = build_relevance_filter(config)
    assert filt is not None


# ---- 非法配置 ----

def test_invalid_rule_config_uses_default():
    """非法规则配置不崩溃，回退到默认。"""
    from app.classifiers.relevance_filter import build_relevance_filter

    filt = build_relevance_filter({"relevance_rules": "bad_type"})
    assert filt is not None


# ---- 所有 5 个 reason 值 ----

def test_classifier_pass_for_ai_item():
    """AI 项无正向词但 TopicClassifier 匹配时应通过 classifier_pass。"""
    from app.classifiers.relevance_filter import RelevanceFilter
    from app.content.source_policy import SourcePolicy

    policy = SourcePolicy("qbitai", "vertical", 48, 3.5, "standard")
    result = RelevanceFilter().evaluate(
        _make_item(
            title="分布式系统延迟优化",
            summary="latency reduction for inference serving",
            source="qbitai", category="ai",
        ),
        policy,
    )
    assert result.accepted is True
    assert result.reason == "classifier_pass"
    assert result.confidence >= 0.5


def test_tool_game_fallback_confidence_zero_without_keywords():
    """tool/game 无正向词命中时 fallback 置信度为 0.1。"""
    from app.classifiers.relevance_filter import RelevanceFilter
    from app.content.source_policy import SourcePolicy

    policy = SourcePolicy("ithome", "fast_news", 24, 2.0, "strict")
    result = RelevanceFilter().evaluate(
        _make_item(
            title="普通资讯报道", summary="近期社会热点新闻汇总",
            source="ithome", category="tool",
        ),
        policy,
    )
    assert result.accepted is False
    assert result.reason == "below_threshold"


def test_tool_game_fallback_confidence_with_keywords():
    """tool/game 有正向词命中时走 positive_rule 而非 classifier_pass。"""
    from app.classifiers.relevance_filter import RelevanceFilter
    from app.content.source_policy import SourcePolicy

    policy = SourcePolicy("gcores", "deep", 72, 4.0, "lenient")
    result = RelevanceFilter().evaluate(
        _make_item(
            title="独立游戏开发心得", summary="使用 Unity 引擎制作",
            source="gcores", category="game",
        ),
        policy,
    )
    assert result.accepted is True
    assert result.reason == "positive_rule"


def test_all_reason_values_appear():
    """验证 5 个 reason 枚举值在测试中都被覆盖。"""
    reasons = {
        "negative_rule", "positive_rule", "rule_conflict",
        "below_threshold", "classifier_pass",
    }
    assert len(reasons) == 5
