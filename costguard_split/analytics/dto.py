"""P1B-01 OPEN analytics read DTOs.

Read-only OPEN analytics layer.

This module contains analytics DTO definitions only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class UsageTotals:
    events: int = 0
    request_count: int = 0

    input_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0

    # Sum of already stored public estimates only.
    # None means no complete public cost data exists.
    public_cost_sum_nullable: Optional[str] = None


@dataclass(frozen=True)
class DimensionSummary:
    key: str | None

    events: int = 0
    request_count: int = 0

    input_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0


@dataclass(frozen=True)
class AnalyticsSummary:
    totals: UsageTotals

    by_provider: list[DimensionSummary] = field(default_factory=list)
    by_model: list[DimensionSummary] = field(default_factory=list)
    by_member: list[DimensionSummary] = field(default_factory=list)
    by_device: list[DimensionSummary] = field(default_factory=list)
