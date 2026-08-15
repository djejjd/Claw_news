from __future__ import annotations


class SourceRegistryAdapter:
    """将运行时采集配置转换为发布库使用的稳定来源记录。"""

    @staticmethod
    def from_feed_configuration(configuration: dict | None) -> list[dict]:
        configuration = configuration or {}
        feeds_by_category = configuration.get("feeds", {})
        if not feeds_by_category:
            from collectors.ai_rss import load_all_rss_feeds

            feeds_by_category = {}
            for feed in load_all_rss_feeds():
                category = feed.get("category")
                if category:
                    feeds_by_category.setdefault(category, []).append(feed)
        by_name: dict[str, dict] = {}
        for category, feeds in feeds_by_category.items():
            if not isinstance(feeds, list):
                continue
            for feed in feeds:
                if not isinstance(feed, dict) or not feed.get("source"):
                    continue
                name = feed["source"]
                spec = by_name.setdefault(
                    name,
                    {
                        "name": name,
                        "display_name": feed.get("display_name", name),
                        "default_category": feed.get("category", category),
                        "site_url": feed.get("site_url"),
                        "feeds": [],
                    },
                )
                strategy = {
                    key: value
                    for key, value in feed.items()
                    if key
                    in {
                        "tier",
                        "retention_hours",
                        "quality_weight",
                        "filter_profile",
                        "max_selected_per_digest",
                        "dynamic_category",
                    }
                }
                spec["feeds"].append(
                    {
                        "url": feed.get("url", ""),
                        "collector_type": "rss",
                        "strategy": strategy,
                    }
                )
        for name, policy in configuration.get("source_policies", {}).items():
            if not isinstance(policy, dict):
                continue
            source_name = policy.get("source", name)
            spec = by_name.setdefault(
                source_name,
                {
                    "name": source_name,
                    "display_name": source_name,
                    "default_category": policy.get("category", "tool"),
                    "site_url": None,
                    "feeds": [],
                },
            )
            spec["feeds"].append(
                {
                    "url": policy.get("url", ""),
                    "collector_type": source_name,
                    "strategy": {key: value for key, value in policy.items() if key != "source"},
                }
            )
        for name, category, url, collector_type in (
            ("huggingface", "ai", "https://huggingface.co/api/daily_papers", "api"),
            ("taptap", "game", "https://www.taptap.cn/top/download", "crawler"),
            ("github", "tool", "https://api.github.com/search/repositories", "api"),
        ):
            spec = by_name.setdefault(
                name,
                {
                    "name": name,
                    "display_name": name,
                    "default_category": category,
                    "site_url": None,
                    "feeds": [{"url": url, "collector_type": collector_type, "strategy": {}}],
                },
            )
            if not any(feed.get("url") for feed in spec["feeds"]):
                spec["feeds"] = [
                    {
                        "url": url,
                        "collector_type": collector_type,
                        "strategy": spec["feeds"][0]["strategy"],
                    }
                ]
        return list(by_name.values())
