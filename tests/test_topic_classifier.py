"""Tests for TopicClassifier — rule-based topic classification."""

from __future__ import annotations

from app.classifiers.topic_classifier import TopicClassifier
from app.pipeline.candidate import CandidateItem

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_item(
    title: str,
    source: str = "rss",
    category: str = "ai",
    summary: str = "",
    url: str = "https://example.com/test",
) -> CandidateItem:
    return CandidateItem(
        title=title,
        url=url,
        summary=summary,
        source=source,
        category=category,
    )


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


class TestTopicClassifier:
    """Unit tests for TopicClassifier."""

    def test_model_release_hit_huggingface_plus_release(self):
        """model_release: source=huggingface + title contains 'release' keyword."""
        classifier = TopicClassifier()
        item = _make_item(
            title="New AI Release",
            source="huggingface",
            summary="A new model was released today",
        )
        result = classifier.classify(item)
        assert result.topic == "model_release"
        # source(1) + title keyword "release"(1) = 2 → 0.9
        assert result.topic_confidence == 0.9

    def test_agent_workflow_hit(self):
        """agent_workflow: title contains 'agent' and 'workflow'."""
        classifier = TopicClassifier()
        item = _make_item(title="AI agent workflow revolution")
        result = classifier.classify(item)
        assert result.topic == "agent_workflow"
        # title hits: agent(1) + workflow(1) = 2 → 0.9
        assert result.topic_confidence == 0.9

    def test_developer_tooling_hit(self):
        """developer_tooling: title contains 'copilot' and 'IDE'."""
        classifier = TopicClassifier()
        item = _make_item(title="GitHub Copilot IDE integration")
        result = classifier.classify(item)
        assert result.topic == "developer_tooling"
        # title hits: copilot(1) + ide(1) + github(1) = 3 → 0.9
        assert result.topic_confidence == 0.9

    def test_research_benchmark_hit(self):
        """research_benchmark: title contains 'benchmark' and 'SOTA'."""
        classifier = TopicClassifier()
        item = _make_item(title="New benchmark achieves SOTA results")
        result = classifier.classify(item)
        assert result.topic == "research_benchmark"
        # title hits: benchmark(1) + sota(1) = 2 → 0.9
        assert result.topic_confidence == 0.9

    def test_infrastructure_hit(self):
        """infrastructure: title contains 'GPU'."""
        classifier = TopicClassifier()
        item = _make_item(title="GPU training optimization")
        result = classifier.classify(item)
        assert result.topic == "infrastructure"
        # title hits: gpu(1) = 1 → 0.7
        assert result.topic_confidence == 0.7

    def test_application_case_fallback_no_match(self):
        """application_case fallback: no keywords match any bucket."""
        classifier = TopicClassifier()
        item = _make_item(
            title="Random unrelated news",
            source="rss",
            category="game",
            summary="Nothing AI-related here",
        )
        result = classifier.classify(item)
        assert result.topic == "application_case"
        assert result.topic_confidence == 0.1

    def test_priority_order_first_match_wins(self):
        """When multiple buckets could match, the first in priority order wins."""
        classifier = TopicClassifier()
        # "GPT agent workflow" with huggingface source:
        # - model_release: matches via gpt + huggingface (priority 1)
        # - agent_workflow: would match via agent, workflow (priority 2)
        item = _make_item(
            title="GPT agent workflow tool",
            source="huggingface",
        )
        result = classifier.classify(item)
        assert result.topic == "model_release"
        # source(1) + title "gpt"(1) = 2 → 0.9
        assert result.topic_confidence == 0.9

    def test_topic_confidence_tiers(self):
        """Verify all confidence tiers are calculated correctly."""
        classifier = TopicClassifier()

        # Tier 0.9: source + title >= 2
        item1 = _make_item(
            title="model release weights",
            source="huggingface",
            summary="",
        )
        result1 = classifier.classify(item1)
        assert result1.topic == "model_release"
        # source(1) + title hits model(1)+release(1)+weights(1) = 4 >= 2
        assert result1.topic_confidence == 0.9

        # Tier 0.7: title only (no source match)
        item2 = _make_item(
            title="AI agent",
            source="rss",
            summary="",
        )
        result2 = classifier.classify(item2)
        assert result2.topic == "agent_workflow"
        # title hits: agent(1) = 1, source_hit=False → 0.7
        assert result2.topic_confidence == 0.7

        # Tier 0.5: summary only (infrastructure keywords in summary)
        item3 = _make_item(
            title="Hello world",
            source="rss",
            summary="Deploying on GPU clusters for inference",
        )
        result3 = classifier.classify(item3)
        assert result3.topic == "infrastructure"
        # title hits: 0, summary hits: gpu + cluster + 推理 + 部署 → multiple > 0
        # summary_count >= 1 → 0.5
        assert result3.topic_confidence == 0.5

        # Tier 0.3: source only (application_case with category=ai, no title match)
        item4 = _make_item(
            title="Just some news",
            source="qbitai",
            category="ai",
            summary="General AI news without specific keywords",
        )
        result4 = classifier.classify(item4)
        # category=ai triggers application_case source_hit
        # title "Just some news" has no app_case keywords → title_count=0
        assert result4.topic == "application_case"
        assert result4.topic_confidence == 0.3

    def test_classify_batch(self):
        """classify_batch processes multiple items correctly."""
        classifier = TopicClassifier()
        items = [
            _make_item(title="GPT model release", source="huggingface"),
            _make_item(title="AI agent workflow"),
            _make_item(title="Copilot IDE debug tool"),
            _make_item(title="Random game news", source="rss", category="game"),
        ]
        results = classifier.classify_batch(items)
        assert len(results) == 4
        assert results[0].topic == "model_release"
        assert results[1].topic == "agent_workflow"
        assert results[2].topic == "developer_tooling"
        assert results[3].topic == "application_case"
        # Verify in-place modification
        assert items[0].topic == "model_release"
        assert items[0] is results[0]
