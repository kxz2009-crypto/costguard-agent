"""P1C-02 OPEN trend visualization adapter.

Thin HTTP adapter only.

Rules:
- no SQL
- no direct database access
- no aggregation
- no cost calculation
- no intelligence layer
"""

from __future__ import annotations

from fastapi import HTTPException

from ..analytics.timeseries import timeseries_summary


def _check_org(context, org_id: str):
    if context is not None:
        if org_id != context.organization_id:
            raise HTTPException(
                status_code=404,
                detail="not found",
            )


def add_trend_visualization_routes(
    app,
    router,
    db,
    context,
):

    @router.get("/visualization/trend")
    def trend_visualization_api(
        org_id: str,
        start: str,
        end: str,
        interval: str,
    ):
        _check_org(context, org_id)

        if interval not in ("day", "hour"):
            raise HTTPException(
                status_code=400,
                detail="unsupported interval",
            )

        result = timeseries_summary(
            db,
            organization_id=org_id,
            start=start,
            end=end,
            granularity=interval,
        )

        return [
            {
                "bucket_start": item.bucket_start,
                "bucket_end": item.bucket_end,
                "events": item.events,
                "request_count": item.request_count,
                "input_tokens": item.input_tokens,
                "cached_input_tokens": item.cached_input_tokens,
                "cache_write_tokens": item.cache_write_tokens,
                "output_tokens": item.output_tokens,
                "reasoning_tokens": item.reasoning_tokens,
                "public_cost_nullable":
                    item.public_cost_nullable,
            }
            for item in result
        ]
