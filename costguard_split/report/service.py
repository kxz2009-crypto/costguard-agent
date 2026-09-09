"""P1D-03 OPEN report generation service.

Deterministic Markdown rendering of existing analytics read models.

No database access.
No aggregation logic.
No pricing logic.
No interpretation.
No file writes.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from costguard_split.analytics.service import analytics_summary
from costguard_split.analytics.timeseries import timeseries_summary
from costguard_split.report.dto import ReportDocument, ReportMeta
from costguard_split.visualization.service import (
    model_distribution,
    provider_distribution,
    visualization_summary,
)

SCHEMA_VERSION = "1"

# Baseline tag this layer was specified against.
BASELINE = "v0.6.1-p1d02"

# Column orders are fixed: mirror asdict() key order of the
# underlying DTOs so the tables stay stable across renders.

_TOTALS_COLUMNS = (
    "events",
    "tokens",
    "public_cost_nullable",
)

_DIMENSION_COLUMNS = ("key", "events", "tokens")

_TREND_COLUMNS = (
    "bucket_start",
    "bucket_end",
    "events",
    "request_count",
    "input_tokens",
    "cached_input_tokens",
    "cache_write_tokens",
    "output_tokens",
    "reasoning_tokens",
    "public_cost_nullable",
)


def _cell(value) -> str:
    """Render one table cell; None renders as an empty cell."""
    if value is None:
        return ""
    return str(value)


def _markdown_table(columns, rows) -> str:
    header = "| " + " | ".join(columns) + " |"
    divider = "|" + "|".join(["---"] * len(columns)) + "|"
    lines = [header, divider]
    for row in rows:
        lines.append(
            "| " + " | ".join(_cell(row.get(column)) for column in columns)
            + " |")
    return "\n".join(lines)


def _body_hash(body: str) -> str:
    encoded = json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _build_document(
    meta: ReportMeta,
    body: str,
) -> ReportDocument:
    return ReportDocument(
        meta=meta,
        body=body,
        content_hash=_body_hash(body),
    )


def _filters_meta(
    meta: ReportMeta,
    provider,
    model,
    member_id,
    device_id,
) -> ReportMeta:
    return ReportMeta(
        schema_version=meta.schema_version,
        baseline=meta.baseline,
        window_start=meta.window_start,
        window_end=meta.window_end,
        granularity=meta.granularity,
        provider=provider,
        model=model,
        member_id=member_id,
        device_id=device_id,
    )


def summary_report(
    db,
    organization_id: str,
    start: str,
    end: str,
    provider: str | None = None,
    model: str | None = None,
    member_id: str | None = None,
    device_id: str | None = None,
) -> ReportDocument:
    """Render the existing analytics summary as a static report."""
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

    totals = visualization_summary(summary)
    totals_row = asdict(totals)

    providers = [asdict(point) for point in provider_distribution(summary)]
    models = [asdict(point) for point in model_distribution(summary)]

    parts = [
        "# Usage Report",
        "",
        "## Totals",
        "",
        _markdown_table(_TOTALS_COLUMNS, [totals_row]),
        "",
        "## Providers",
        "",
        _markdown_table(_DIMENSION_COLUMNS, providers),
        "",
        "## Models",
        "",
        _markdown_table(_DIMENSION_COLUMNS, models),
        "",
    ]
    body = "\n".join(parts)

    meta = _filters_meta(
        ReportMeta(
            schema_version=SCHEMA_VERSION,
            baseline=BASELINE,
            window_start=start,
            window_end=end,
        ),
        provider,
        model,
        member_id,
        device_id,
    )
    return _build_document(meta, body)


def timeseries_report(
    db,
    organization_id: str,
    start: str,
    end: str,
    granularity: str,
) -> ReportDocument:
    """Render the existing time series as a static report.

    Point order is preserved exactly as produced by
    timeseries_summary. Unsupported granularity surfaces the
    existing timeseries error unchanged.
    """
    points = timeseries_summary(
        db,
        organization_id=organization_id,
        start=start,
        end=end,
        granularity=granularity,
    )

    rows = [asdict(point) for point in points]

    parts = [
        "# Usage Timeseries Report",
        "",
        _markdown_table(_TREND_COLUMNS, rows),
        "",
    ]
    body = "\n".join(parts)

    meta = ReportMeta(
        schema_version=SCHEMA_VERSION,
        baseline=BASELINE,
        window_start=start,
        window_end=end,
        granularity=granularity,
    )
    return _build_document(meta, body)
