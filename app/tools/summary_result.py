from dataclasses import dataclass, field


@dataclass
class SummaryItem:
    title: str
    url: str
    core_summary: str
    importance: str  # 高/中/低
    trend: str


@dataclass
class SummaryResult:
    headline_items: list  # list[SummaryItem]
    daily_judgement: str


@dataclass
class PublishResult:
    status: str  # ok | failed | skipped
    selected_count: int
    pushed: bool
    message_type: str  # markdown
    summary_preview: str
    errors: list = field(default_factory=list)


@dataclass
class DigestPayload:
    date: str
    period: str
    published_at: str
    trigger_mode: str
    headline_items: list = field(default_factory=list)
    daily_judgement: str = ""
    source_failures: list = field(default_factory=list)
    published_urls: list = field(default_factory=list)
    published_keys: list = field(default_factory=list)
