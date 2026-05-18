from dataclasses import dataclass
from typing import Literal

TriggerMode = Literal["scheduler", "http", "cli_compat"]
Period = Literal["morning"]
PublishScope = Literal["ai_only"]
StateNamespace = Literal["ai_digest"]


@dataclass(frozen=True)
class RunContext:
    trigger_mode: TriggerMode
    period: Period = "morning"
    time_window_start: str = ""  # ISO format datetime string, 当前发布日 00:00:00
    time_window_end: str = ""  # ISO format datetime string, 触发时刻
    publish_scope: PublishScope = "ai_only"
    state_namespace: StateNamespace = "ai_digest"
