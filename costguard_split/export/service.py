"""P1D-01 OPEN analytics export service.

Deterministic serialization of existing analytics read models.

This layer consumes existing analytics and visualization services only.

No database access.
No aggregation logic.
No pricing logic.
No mutation of analytics state.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from costguard_split.analytics.service import analytics_summary
from costguard_split.analytics.timeseries import timeseries_summary
from costguard_split.export.dto import ExportDocument, ExportManifest
from costguard_split.visualization.service import (
    model_distribution,
    provider_distribution,
    visualization_summary,
)

SCHEMA_VERSION = "1"

# Baseline tag this layer was specified against.
BASELINE = "v0.5.1-p1c02"


def _canonical_hash(payload) -> str:
    """sha256 over canonical JSON bytes of the payload."""
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _build_document(
    generated_from: str,
    start: str,
    end: str,
    payload,
    provider=None,
    model=None,
    member_id=None,
    device_id=None,
) -> ExportDocument:
    manifest = ExportManifest(
        schema_version=SCHEMA_VERSION,
        generated_from=generated_from,
        baseline=BASELINE,
        window_start=start,
        window_end=end,
        provider=provider,
        model=model,
        member_id=member_id,
        device_id=device_id,
        content_hash=_canonical_hash(payload),
    )
    return ExportDocument(manifest=manifest, payload=payload)


def summary_export(
    db,
    organization_id: str,
    start: str,
    end: str,
    provider: str | None = None,
    model: str | None = None,
    member_id: str | None = None,
    device_id: str | None = None,
) -> ExportDocument:
    """Export the existing analytics summary read model as a document."""
    summary = analytics_summary(
        db,
        organization_id,
        start,
        end,
        provider=provider,
        model=model,
        member_id=member_id,
        device_id=device_id,
    )
    payload = asdict(summary)
    return _build_document(
        generated_from="analytics",
        start=start,
        end=end,
        payload=payload,
        provider=provider,
        model=model,
        member_id=member_id,
        device_id=device_id,
    )


def timeseries_export(
    db,
    organization_id: str,
    start: str,
    end: str,
    granularity: str,
) -> ExportDocument:
    """Export the existing time series read model as a document.

    Point order is preserved exactly as produced by timeseries_summary.
    """
    points = timeseries_summary(
        db,
        organization_id,
        start,
        end,
        granularity,
    )
    payload = [asdict(point) for point in points]
    return _build_document(
        generated_from="timeseries",
        start=start,
        end=end,
        payload=payload,
    )


def distribution_export(
    db,
    organization_id: str,
    start: str,
    end: str,
    provider: str | None = None,
    model: str | None = None,
    member_id: str | None = None,
    device_id: str | None = None,
) -> ExportDocument:
    """Export provider/model distributions built on the analytics summary."""
    summary = analytics_summary(
        db,
        organization_id,
        start,
        end,
        provider=provider,
        model=model,
        member_id=member_id,
        device_id=device_id,
    )

    payload = {
        "summary": asdict(visualization_summary(summary)),
        "provider_distribution": [
            asdict(point) for point in provider_distribution(summary)
        ],
        "model_distribution": [
            asdict(point) for point in model_distribution(summary)
        ],
    }
    return _build_document(
        generated_from="distribution",
        start=start,
        end=end,
        payload=payload,
        provider=provider,
        model=model,
        member_id=member_id,
        device_id=device_id,
    )
