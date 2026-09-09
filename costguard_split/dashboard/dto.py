"""P1D-02 OPEN dashboard read DTOs.

Dashboard payload envelope definitions.

This module contains dashboard DTO definitions only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class DashboardMeta:
    """Integrity block describing the dashboard payload."""

    schema_version: str
    baseline: str
    window_start: str
    window_end: str
    granularity: str

    provider: Optional[str] = None
    model: Optional[str] = None
    member_id: Optional[str] = None
    device_id: Optional[str] = None


@dataclass(frozen=True)
class DashboardPayload:
    """Dashboard-ready read model assembled from existing layers."""

    meta: DashboardMeta
    totals: dict = field(default_factory=dict)
    provider_distribution: list = field(default_factory=list)
    model_distribution: list = field(default_factory=list)
    trend: list = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Canonical dict representation with stable section keys."""
        return {
            "meta": {
                "schema_version": self.meta.schema_version,
                "baseline": self.meta.baseline,
                "window": {
                    "start": self.meta.window_start,
                    "end": self.meta.window_end,
                },
                "granularity": self.meta.granularity,
                "filters": {
                    "provider": self.meta.provider,
                    "model": self.meta.model,
                    "member_id": self.meta.member_id,
                    "device_id": self.meta.device_id,
                },
            },
            "totals": dict(self.totals),
            "provider_distribution": [
                dict(point) for point in self.provider_distribution
            ],
            "model_distribution": [
                dict(point) for point in self.model_distribution
            ],
            "trend": [dict(point) for point in self.trend],
            "extra": dict(self.extra),
        }
