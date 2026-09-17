"""P1B-02 OPEN visualization DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class UsageTrendPoint:
    date: str
    events: int = 0
    tokens: int = 0
    public_cost_nullable: Optional[str] = None


@dataclass(frozen=True)
class DistributionPoint:
    dimension: str
    key: Optional[str]

    events: int = 0
    tokens: int = 0


@dataclass(frozen=True)
class VisualizationSummary:
    events: int = 0
    tokens: int = 0
    public_cost_nullable: Optional[str] = None
