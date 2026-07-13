"""Secret-free state for independently delivered digest channels."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Literal

ChannelStatus = Literal["pending", "succeeded", "failed"]
_VALID_STATUSES = {"pending", "succeeded", "failed"}


@dataclass(frozen=True)
class ChannelResult:
    enabled: bool
    status: ChannelStatus
    attempted_at: str | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if self.status not in _VALID_STATUSES:
            raise ValueError(f"unsupported delivery channel status: {self.status}")


@dataclass
class DeliveryState:
    delivery_id: str
    channels: dict[str, ChannelResult]

    def can_attempt(self, channel: str) -> bool:
        result = self.channels.get(channel)
        return result is not None and result.enabled and result.status != "succeeded"

    def to_dict(self) -> dict[str, object]:
        return {
            "delivery_id": self.delivery_id,
            "channels": {name: asdict(result) for name, result in self.channels.items()},
        }


def make_delivery_id(date: str, period: str, content: str) -> str:
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    return f"{date}-{period}-{content_hash}"
