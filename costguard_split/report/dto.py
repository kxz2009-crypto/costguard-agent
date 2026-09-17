"""P1D-03 OPEN report DTOs.

Static report envelope definitions.

This module contains report DTO definitions only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class ReportMeta:
    """Integrity block describing the rendered report."""

    schema_version: str
    baseline: str
    window_start: str
    window_end: str

    granularity: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    member_id: Optional[str] = None
    device_id: Optional[str] = None


@dataclass(frozen=True)
class ReportDocument:
    """Deterministic report envelope: meta + hashed markdown body."""

    meta: ReportMeta
    body: str = ""
    content_hash: str = ""

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
            "content_hash": self.content_hash,
            "body": self.body,
        }
