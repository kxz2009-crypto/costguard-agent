"""P1B-03 OPEN visualization HTTP adapter.

Thin HTTP adapter.

Rules:
- no SQL
- no direct database queries
- no pricing logic
- no business decisions
"""

from __future__ import annotations

from fastapi import HTTPException

from ..analytics.service import analytics_summary
from ..visualization.service import (
    model_distribution,
    provider_distribution,
    visualization_summary,
)


def _check_org(context, org_id: str):
    if context is not None:
        if org_id != context.organization_id:
            raise HTTPException(
                status_code=404,
                detail="not found",
            )


def add_visualization_routes(app, router, db, context):

    @router.get("/visualization/summary")
    def visualization_summary_api(
        org_id: str,
        start: str,
        end: str,
    ):
        _check_org(context, org_id)

        analytics = analytics_summary(
            db,
            organization_id=org_id,
            start=start,
            end=end,
        )

        result = visualization_summary(analytics)

        return {
            "events": result.events,
            "tokens": result.tokens,
            "public_cost_nullable":
                result.public_cost_nullable,
        }


    @router.get("/visualization/providers")
    def visualization_provider_api(
        org_id: str,
        start: str,
        end: str,
    ):
        _check_org(context, org_id)

        analytics = analytics_summary(
            db,
            organization_id=org_id,
            start=start,
            end=end,
        )

        return [
            {
                "provider": item.key,
                "events": item.events,
                "tokens": item.tokens,
            }
            for item in provider_distribution(analytics)
        ]


    @router.get("/visualization/models")
    def visualization_model_api(
        org_id: str,
        start: str,
        end: str,
    ):
        _check_org(context, org_id)

        analytics = analytics_summary(
            db,
            organization_id=org_id,
            start=start,
            end=end,
        )

        return [
            {
                "model": item.key,
                "events": item.events,
                "tokens": item.tokens,
            }
            for item in model_distribution(analytics)
        ]
