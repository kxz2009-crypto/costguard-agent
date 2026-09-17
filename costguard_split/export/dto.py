"""P1D-01 OPEN analytics export DTOs.

Read-only export envelope definitions.

This module contains export DTO definitions only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class ExportManifest:
    """Integrity block describing the exported payload."""

    schema_version: str
    generated_from: str
    baseline: str
    window_start: str
    window_end: str

    provider: Optional[str] = None
    model: Optional[str] = None
    member_id: Optional[str] = None
    device_id: Optional[str] = None

    content_hash: str = ""


@dataclass(frozen=True)
class ExportDocument:
    """Deterministic export envelope: manifest + payload."""

    manifest: ExportManifest
    payload: Any = field(default=None)

    def to_dict(self) -> dict:
        """Canonical dict representation with sorted, stable keys."""
        return {
            "manifest": {
                "schema_version": self.manifest.schema_version,
                "generated_from": self.manifest.generated_from,
                "baseline": self.manifest.baseline,
                "window": {
                    "start": self.manifest.window_start,
                    "end": self.manifest.window_end,
                },
                "filters": {
                    "provider": self.manifest.provider,
                    "model": self.manifest.model,
                    "member_id": self.manifest.member_id,
                    "device_id": self.manifest.device_id,
                },
                "content_hash": self.manifest.content_hash,
            },
            "payload": self.payload,
        }
