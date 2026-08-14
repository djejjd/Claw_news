"""综合来源的内容级分类，不访问网络且不改变未启用来源的默认类别。"""

from __future__ import annotations

from collections.abc import Mapping, Set

from app.pipeline.candidate import CandidateItem


class ContentCategoryClassifier:
    """仅对配置允许的综合来源按标题和摘要重分类。"""

    _RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
        (
            "ai",
            (
                "openai",
                "大模型",
                "llm",
                "gpt",
                "claude",
                "gemini",
                "人工智能",
                "生成式 ai",
                "生成式ai",
                "智能体",
                "agent",
                "机器学习",
            ),
        ),
        (
            "game",
            ("游戏", "新游", "steam", "主机", "ps5", "xbox", "switch", "dlc", "电竞"),
        ),
        (
            "tool",
            ("开源", "命令行", "终端", "编程", "代码", "开发者", "ide", "插件", "软件工具"),
        ),
        (
            "digital",
            ("手机", "笔记本", "平板", "芯片", "处理器", "macbook", "电脑", "操作系统", "os"),
        ),
    )

    def classify_batch(
        self,
        items: list[CandidateItem],
        *,
        dynamic_sources: Set[str],
    ) -> list[CandidateItem]:
        for item in items:
            if item.source not in dynamic_sources:
                continue
            category = self._classify(item)
            if category is not None:
                item.category = category
        return items

    def _classify(self, item: CandidateItem) -> str | None:
        text = f"{item.title} {item.summary or ''}".lower()
        for category, keywords in self._RULES:
            if any(keyword in text for keyword in keywords):
                return category
        return None


def dynamic_sources_from_feed_config(config: Mapping[str, object]) -> set[str]:
    """从 feeds 配置读取允许内容级重分类的来源。"""
    feeds = config.get("feeds", {})
    if not isinstance(feeds, Mapping):
        return set()

    sources: set[str] = set()
    for entries in feeds.values():
        if not isinstance(entries, list):
            continue
        for feed in entries:
            if not isinstance(feed, Mapping) or not feed.get("dynamic_category"):
                continue
            source = feed.get("source")
            if isinstance(source, str) and source:
                sources.add(source)
    return sources
