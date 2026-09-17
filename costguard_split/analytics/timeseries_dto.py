"""P1C-01 OPEN time series analytics DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TimeSeriesPoint:
    bucket_start: str
    bucket_end: str

    events: int = 0
    request_count: int = 0

    input_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0

    public_cost_nullable: Optional[str] = None
