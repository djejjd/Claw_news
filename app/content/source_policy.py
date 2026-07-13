"""来源策略 registry — 质量权重、有效期与相关性 profile。

本模块维护来源策略的默认值和校验逻辑。
不替代 app/ingest/source_policy.py 的采集准入语义。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Tier = Literal["fast_news", "vertical", "deep"]
FilterProfile = Literal["strict", "standard", "lenient"]

_VALID_TIERS: frozenset[str] = frozenset({"fast_news", "vertical", "deep"})
_VALID_PROFILES: frozenset[str] = frozenset({"strict", "standard", "lenient"})


@dataclass(frozen=True)
class SourcePolicy:
    """单一来源的推送策略。"""

    source: str
    tier: Tier = "vertical"
    retention_hours: int = 48
    quality_weight: float = 3.0
    filter_profile: FilterProfile = "standard"


DEFAULT_SOURCE_POLICY = SourcePolicy(source="")

_BUILTIN_SOURCE_POLICIES: dict[str, SourcePolicy] = {
    "ithome": SourcePolicy("ithome", "fast_news", 24, 2.0, "strict"),
    "taptap": SourcePolicy("taptap", "fast_news", 24, 2.5, "strict"),
    "eurogamer": SourcePolicy("eurogamer", "fast_news", 24, 3.0, "strict"),
    "qbitai": SourcePolicy("qbitai", "vertical", 48, 3.5, "standard"),
    "leiphone": SourcePolicy("leiphone", "vertical", 48, 3.5, "standard"),
    "jiqizhixin": SourcePolicy("jiqizhixin", "vertical", 48, 3.5, "standard"),
    "sspai": SourcePolicy("sspai", "vertical", 48, 3.5, "standard"),
    "appinn": SourcePolicy("appinn", "vertical", 48, 3.5, "standard"),
    "yystv": SourcePolicy("yystv", "vertical", 48, 3.5, "standard"),
    "indienova": SourcePolicy("indienova", "vertical", 48, 3.5, "standard"),
    "gcores": SourcePolicy("gcores", "deep", 72, 4.0, "lenient"),
    "chuapp": SourcePolicy("chuapp", "deep", 72, 4.0, "lenient"),
    "meituan_tech": SourcePolicy("meituan_tech", "deep", 72, 4.0, "lenient"),
    "cloudflare_cn": SourcePolicy("cloudflare_cn", "deep", 72, 4.0, "lenient"),
    "huggingface": SourcePolicy("huggingface", "deep", 72, 4.0, "lenient"),
}


def build_source_policy_registry(feeds: list[dict]) -> dict[str, SourcePolicy]:
    """从 feed 列表构建 {source: SourcePolicy} registry。

    feed 中可选的策略字段：tier, retention_hours, quality_weight, filter_profile。
    缺少时使用 SourcePolicy 默认值。
    非法值抛出 ValueError 并指明 source 和字段。
    """
    registry: dict[str, SourcePolicy] = {}
    for feed in feeds:
        source = feed.get("source", "")
        if not source:
            continue

        # 解析字段，保留显式配置值
        tier = feed.get("tier", "vertical")
        retention_hours = feed.get("retention_hours", 48)
        quality_weight = feed.get("quality_weight", 3.0)
        filter_profile = feed.get("filter_profile", "standard")

        # 校验
        if tier not in _VALID_TIERS:
            raise ValueError(
                f"Source '{source}': invalid tier '{tier}', must be one of {sorted(_VALID_TIERS)}"
            )
        if (
            isinstance(retention_hours, bool)
            or not isinstance(retention_hours, int)
            or retention_hours <= 0
        ):
            raise ValueError(
                f"Source '{source}': retention_hours must be a positive integer, "
                f"got {retention_hours}"
            )
        if not isinstance(quality_weight, (int, float)) or quality_weight < 0:
            raise ValueError(
                f"Source '{source}': quality_weight must be >= 0, got {quality_weight}"
            )
        if filter_profile not in _VALID_PROFILES:
            raise ValueError(
                f"Source '{source}': invalid filter_profile '{filter_profile}', "
                f"must be one of {sorted(_VALID_PROFILES)}"
            )

        registry[source] = SourcePolicy(
            source=source,
            tier=tier,  # type: ignore[arg-type]
            retention_hours=retention_hours,
            quality_weight=float(quality_weight),
            filter_profile=filter_profile,  # type: ignore[arg-type]
        )
    return registry


def resolve_source_policy(source: str, registry: dict[str, SourcePolicy]) -> SourcePolicy:
    """从 registry 查找 source 的策略；未找到时返回保守默认值。"""
    if source in registry:
        return registry[source]
    if source in _BUILTIN_SOURCE_POLICIES:
        return _BUILTIN_SOURCE_POLICIES[source]
    return SourcePolicy(source=source)  # uses DEFAULT_SOURCE_POLICY field defaults
