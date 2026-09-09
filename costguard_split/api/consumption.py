"""P1D-04 OPEN open consumption API adapter.

Versioned read-only HTTP exposure of existing read models.

Rules:
- no SQL
- no direct database access
- no aggregation
- no cost calculation
- no intelligence layer
- stricter tenant guard than legacy visualization adapters:
  a missing (None) ServerContext is a 404, never a bypass
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, Request, Response
from fastapi.datastructures import FormData
from starlette.middleware.base import BaseHTTPMiddleware

from ..analytics.service import analytics_summary
from ..analytics.timeseries import timeseries_summary
from ..dashboard.service import dashboard_projection
from ..export.service import (
    distribution_export,
    summary_export,
    timeseries_export,
)
from ..report.service import summary_report, timeseries_report
from ..visualization.service import (
    model_distribution,
    provider_distribution,
)

CONSUMPTION_PREFIX = "/api/v1/consumption"

GRANULARITIES = ("day", "hour")
MAX_WINDOW_DAYS = 31


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="not found")


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail=message)


def _require_context(context, org_id: str) -> None:
    """Stricter tenant guard for consumption routes.

    Unlike the legacy visualization _check_org, a None context is
    a hard 404. Client input can never create or select context.
    """
    if context is None:
        raise _not_found()
    if org_id != context.organization_id:
        raise _not_found()


def _parse_instant(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise _bad_request(f"invalid {field}: not ISO-8601")
    if parsed.tzinfo is None:
        raise _bad_request(f"invalid {field}: timezone-naive")
    return parsed


def _normalize_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _validate_window(start: str, end: str) -> tuple[str, str]:
    """Validate and normalize the window to UTC ISO strings.

    Window is [start, end); start < end; max 31 days.
    """
    start_dt = _parse_instant(start, "start")
    end_dt = _parse_instant(end, "end")

    if start_dt >= end_dt:
        raise _bad_request("invalid window: start must precede end")

    if (end_dt - start_dt).days > MAX_WINDOW_DAYS:
        raise _bad_request(
            f"invalid window: exceeds {MAX_WINDOW_DAYS} days")

    return _normalize_utc(start_dt), _normalize_utc(end_dt)


def _validate_granularity(granularity: str) -> None:
    if granularity not in GRANULARITIES:
        raise _bad_request("unsupported granularity")


def _reject_dashboard_filters(
    provider, model, member_id, device_id
) -> None:
    provided = [name for name, value in (
        ("provider", provider),
        ("model", model),
        ("member_id", member_id),
        ("device_id", device_id),
    ) if value is not None]
    if provided:
        raise HTTPException(
            status_code=422,
            detail=(
                "dashboard filters not supported: "
                + ", ".join(provided)
            ),
        )


class _NoStoreMiddleware(BaseHTTPMiddleware):
    """Attach Cache-Control: no-store to consumption responses.

    Scoped strictly to the consumption prefix so legacy routes
    keep their exact transport behavior. Middleware level so it
    also covers framework-generated validation (422) responses.
    """

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        if request.url.path.startswith(CONSUMPTION_PREFIX):
            response.headers["Cache-Control"] = "no-store"
        return response


def _dimension_rows(points):
    return [
        {
            "dimension": point.dimension,
            "key": point.key,
            "events": point.events,
            "tokens": point.tokens,
        }
        for point in points
    ]


def add_consumption_routes(app, router, db, context):

    @router.get("/consumption/summary")
    def consumption_summary_api(
        org_id: str,
        start: str,
        end: str,
        provider: str | None = None,
        model: str | None = None,
        member_id: str | None = None,
        device_id: str | None = None,
    ):
        _require_context(context, org_id)
        norm_start, norm_end = _validate_window(start, end)

        summary = analytics_summary(
            db,
            org_id,
            norm_start,
            norm_end,
            provider=provider,
            model=model,
            member_id=member_id,
            device_id=device_id,
        )
        from dataclasses import asdict
        return asdict(summary)

    @router.get("/consumption/timeseries")
    def consumption_timeseries_api(
        org_id: str,
        start: str,
        end: str,
        granularity: str,
    ):
        _require_context(context, org_id)
        _validate_granularity(granularity)
        norm_start, norm_end = _validate_window(start, end)

        points = timeseries_summary(
            db,
            organization_id=org_id,
            start=norm_start,
            end=norm_end,
            granularity=granularity,
        )
        return [
            {
                "bucket_start": point.bucket_start,
                "bucket_end": point.bucket_end,
                "events": point.events,
                "request_count": point.request_count,
                "input_tokens": point.input_tokens,
                "cached_input_tokens": point.cached_input_tokens,
                "cache_write_tokens": point.cache_write_tokens,
                "output_tokens": point.output_tokens,
                "reasoning_tokens": point.reasoning_tokens,
                "public_cost_nullable": point.public_cost_nullable,
            }
            for point in points
        ]

    @router.get("/consumption/distributions")
    def consumption_distributions_api(
        org_id: str,
        start: str,
        end: str,
        provider: str | None = None,
        model: str | None = None,
        member_id: str | None = None,
        device_id: str | None = None,
    ):
        _require_context(context, org_id)
        norm_start, norm_end = _validate_window(start, end)

        summary = analytics_summary(
            db,
            org_id,
            norm_start,
            norm_end,
            provider=provider,
            model=model,
            member_id=member_id,
            device_id=device_id,
        )
        return {
            "provider_distribution":
                _dimension_rows(provider_distribution(summary)),
            "model_distribution":
                _dimension_rows(model_distribution(summary)),
        }

    @router.get("/consumption/dashboard")
    def consumption_dashboard_api(
        org_id: str,
        start: str,
        end: str,
        granularity: str,
        provider: str | None = None,
        model: str | None = None,
        member_id: str | None = None,
        device_id: str | None = None,
    ):
        _require_context(context, org_id)
        _validate_granularity(granularity)
        norm_start, norm_end = _validate_window(start, end)
        _reject_dashboard_filters(
            provider, model, member_id, device_id)

        payload = dashboard_projection(
            db,
            org_id,
            norm_start,
            norm_end,
            granularity,
        )
        return payload.to_dict()

    @router.get("/consumption/export/summary")
    def consumption_export_summary_api(
        org_id: str,
        start: str,
        end: str,
        provider: str | None = None,
        model: str | None = None,
        member_id: str | None = None,
        device_id: str | None = None,
    ):
        _require_context(context, org_id)
        norm_start, norm_end = _validate_window(start, end)

        document = summary_export(
            db, org_id, norm_start, norm_end,
            provider=provider, model=model,
            member_id=member_id, device_id=device_id,
        )
        return document.to_dict()

    @router.get("/consumption/export/timeseries")
    def consumption_export_timeseries_api(
        org_id: str,
        start: str,
        end: str,
        granularity: str,
    ):
        _require_context(context, org_id)
        _validate_granularity(granularity)
        norm_start, norm_end = _validate_window(start, end)

        document = timeseries_export(
            db, org_id, norm_start, norm_end, granularity,
        )
        return document.to_dict()

    @router.get("/consumption/export/distributions")
    def consumption_export_distributions_api(
        org_id: str,
        start: str,
        end: str,
        provider: str | None = None,
        model: str | None = None,
        member_id: str | None = None,
        device_id: str | None = None,
    ):
        _require_context(context, org_id)
        norm_start, norm_end = _validate_window(start, end)

        document = distribution_export(
            db, org_id, norm_start, norm_end,
            provider=provider, model=model,
            member_id=member_id, device_id=device_id,
        )
        return document.to_dict()

    @router.get("/consumption/report/summary")
    def consumption_report_summary_api(
        org_id: str,
        start: str,
        end: str,
        provider: str | None = None,
        model: str | None = None,
        member_id: str | None = None,
        device_id: str | None = None,
    ):
        _require_context(context, org_id)
        norm_start, norm_end = _validate_window(start, end)

        document = summary_report(
            db, org_id, norm_start, norm_end,
            provider=provider, model=model,
            member_id=member_id, device_id=device_id,
        )
        return document.to_dict()

    @router.get("/consumption/report/timeseries")
    def consumption_report_timeseries_api(
        org_id: str,
        start: str,
        end: str,
        granularity: str,
    ):
        _require_context(context, org_id)
        _validate_granularity(granularity)
        norm_start, norm_end = _validate_window(start, end)

        document = timeseries_report(
            db, org_id, norm_start, norm_end, granularity,
        )
        return document.to_dict()

    # namespace-scoped transport policy (installed with the
    # routes; scoped by path prefix inside the middleware)
    if not any(
        isinstance(m, _NoStoreMiddleware) for m in app.user_middleware
    ):
        app.add_middleware(_NoStoreMiddleware)
