"""P1A canonical server-side usage event domain model.

This model is intentionally independent from ``costguard_agent.UsageEvent``:
Split events carry tenant/device/server identity and use Decimal-safe nullable
money representations. It performs no pricing, ingestion, attribution, or I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

TOKEN_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_tokens",
    "output_tokens",
    "reasoning_tokens",
)


@dataclass(frozen=True)
class UsageEvent:
    """Canonical immutable Usage Event Schema v1 representation."""

    id: str
    organization_id: str
    device_id: str
    device_uid: str
    member_id: Optional[str]
    provider: str
    provider_account_ref: Optional[str]
    model: str
    session_ref: str
    source_event_id: str
    started_at: str
    ended_at: str
    received_at: str
    input_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    request_count: int = 1
    pricing_version: Optional[str] = None
    api_equivalent_cost_usd: Optional[str] = None
    source_type: str = "connector"
    collector_version: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        for name in TOKEN_FIELDS + ("request_count",):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an int")
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
