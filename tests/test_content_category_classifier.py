"""内容级动态分类测试。"""

from app.pipeline.candidate import CandidateItem


def _item(*, title: str, category: str = "digital", source: str = "ithome") -> CandidateItem:
    return CandidateItem(
        title=title,
        url="https://example.test/article",
        summary="内容摘要足够长，可用于规则分类。",
        source=source,
        category=category,
    )


def test_dynamic_category_classifier_reclassifies_only_enabled_sources():
    """综合来源按内容分类，未启用来源保留默认分类。"""
    from app.classifiers.content_category_classifier import ContentCategoryClassifier

    classifier = ContentCategoryClassifier()
    enabled = classifier.classify_batch(
        [_item(title="OpenAI 发布新一代大模型")], dynamic_sources={"ithome"}
    )[0]
    disabled = classifier.classify_batch(
        [_item(title="OpenAI 发布新一代大模型", source="sspai")], dynamic_sources={"ithome"}
    )[0]

    assert enabled.category == "ai"
    assert disabled.category == "digital"


def test_dynamic_category_classifier_covers_tool_game_and_digital():
    """综合来源对四类内容提供可解释重分类结果。"""
    from app.classifiers.content_category_classifier import ContentCategoryClassifier

    classifier = ContentCategoryClassifier()
    items = classifier.classify_batch(
        [
            _item(title="开源命令行工具发布"),
            _item(title="新游登陆 Steam 平台"),
            _item(title="苹果发布新款手机芯片"),
        ],
        dynamic_sources={"ithome"},
    )

    assert [item.category for item in items] == ["tool", "game", "digital"]
