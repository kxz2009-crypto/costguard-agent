"""P1D-02 OPEN dashboard read projection service.

Assembles existing analytics, timeseries and visualization read
models into one dashboard-ready payload.

No database access.
No aggregation logic.
No pricing logic.
No state across calls.
"""

from __future__ import annotations

from dataclasses import asdict

from costguard_split.analytics.service import analytics_summary
from costguard_split.analytics.timeseries import timeseries_summary
from costguard_split.dashboard.dto import DashboardMeta, DashboardPayload
from costguard_split.visualization.service import (
    model_distribution,
    provider_distribution,
    visualization_summary,
)

SCHEMA_VERSION = "1"

# Baseline tag this layer was specified against.
BASELINE = "v0.6.0-p1d01"


def dashboard_projection(
    db,
    organization_id: str,
    start: str,
    end: str,
    granularity: str,
    provider: str | None = None,
    model: str | None = None,
    member_id: str | None = None,
    device_id: str | None = None,
) -> DashboardPayload:
    """Assemble the dashboard payload from existing read models.

    Unsupported granularity is delegated to the timeseries layer:
    its ValueError surfaces unchanged.
    """
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
    providers = provider_distribution(summary)
    models = model_distribution(summary)

    trend_points = timeseries_summary(
        db,
        organization_id=organization_id,
        start=start,
        end=end,
        granularity=granularity,
    )

    meta = DashboardMeta(
        schema_version=SCHEMA_VERSION,
        baseline=BASELINE,
        window_start=start,
        window_end=end,
        granularity=granularity,
        provider=provider,
        model=model,
        member_id=member_id,
        device_id=device_id,
    )

    return DashboardPayload(
        meta=meta,
        totals=asdict(totals),
        provider_distribution=[asdict(point) for point in providers],
        model_distribution=[asdict(point) for point in models],
        trend=[asdict(point) for point in trend_points],
    )
