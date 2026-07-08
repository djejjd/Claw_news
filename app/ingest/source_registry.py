from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class IngestSourceSpec:
    name: str
    collector_cls: type
    collector_kwargs: dict[str, Any]
    optional_env_var: str | None = None


def build_ingest_source_specs(hf_proxy: str | None = None) -> list[IngestSourceSpec]:
    from collectors.ai_rss import load_all_rss_feeds
    from collectors.huggingface import HfDailyPapersCollector
    from collectors.rss_sources import RssCollector
    from collectors.taptap import TapTapCollector

    return [
        IngestSourceSpec(
            name="rss",
            collector_cls=RssCollector,
            collector_kwargs={"feed_configs": load_all_rss_feeds()},
        ),
        IngestSourceSpec(
            name="huggingface",
            collector_cls=HfDailyPapersCollector,
            collector_kwargs={"proxy": hf_proxy},
            optional_env_var="HF_OPTIONAL",
        ),
        IngestSourceSpec(
            name="taptap",
            collector_cls=TapTapCollector,
            collector_kwargs={},
            optional_env_var="TAPTAP_OPTIONAL",
        ),
    ]


def is_optional_source(spec: IngestSourceSpec) -> bool:
    if not spec.optional_env_var:
        return False
    return os.getenv(spec.optional_env_var, "").strip().lower() in {"1", "true", "yes", "on"}
