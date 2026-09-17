"""P1A-07 usage HTTP routes — thin adapter over the P1A-03 ingest service.

No business rule lives here: dedupe, tenant resolution, member_at, server
timestamps, and audit all stay inside ingest_usage_event(). This module
only parses strict DTOs, maps domain outcomes to status codes, and
projects responses.

Error contract (spec section 10, unified with P0):
    201 created            (single POST, first accept)
    200 duplicate          (idempotent retransmit, same event id)
    400 invalid filter     (bad from/to on list)
    404 not found          (TenantViolation — foreign ids hidden)
    409 usage conflict     (IngestConflict — same identity, different facts)
    413 body too large     (batch > 1 MiB, spec section 6.2)
    422 schema validation  (malformed JSON, forbidden/extra fields,
                            batch envelope violations — zero writes)
    500 unexpected         (handled by the app-level handler, no traceback)

Batch semantics (spec section 6.2): <= 500 items, per-item
created|duplicate|rejected results, one rejected item never rolls back
accepted siblings (each item is its own ingest transaction). A
whole-request failure (malformed JSON / bad envelope / > 500 items /
oversize body) is rejected before any write.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Query, Request, Response
from pydantic import ValidationError

from ..ingest.service import IngestConflict, ingest_usage_event
from ..schemas.usage import UsageEventClaim
from .context import TenantViolation
from .schemas import (
    UsageBatchItemResult,
    UsageBatchResponse,
    UsageEventBatchRequest,
    UsageEventResponse,
)

_MAX_BATCH_ITEMS = 500                  # spec section 6.2
_MAX_BODY_BYTES = 1 * 1024 * 1024       # spec section 6.2: 1 MiB

_SELECT_COLUMNS = (
    "id", "organization_id", "device_id", "device_uid", "member_id",
    "provider", "provider_account_ref", "model", "session_ref",
    "source_event_id", "started_at", "ended_at", "received_at",
    "input_tokens", "cached_input_tokens", "cache_write_tokens",
    "output_tokens", "reasoning_tokens", "request_count", "pricing_version",
    "api_equivalent_cost_usd", "source_type", "collector_version",
    "created_at",
)


def _event_response(event) -> UsageEventResponse:
    return UsageEventResponse(**{
        name: getattr(event, name) for name in _SELECT_COLUMNS})


def _row_response(row) -> UsageEventResponse:
    return UsageEventResponse(**dict(zip(_SELECT_COLUMNS, row)))


def _parse_bound(value: Optional[str], name: str) -> Optional[str]:
    """Normalize a filter bound to UTC isoformat (usage_events stores UTC
    isoformat strings, so lexicographic comparison stays chronological)."""
    if value is None:
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={
            "error": "invalid_filter",
            "message": f"{name} must be an ISO8601 timestamp"}) from exc
    if parsed.tzinfo is None:
        raise HTTPException(status_code=400, detail={
            "error": "invalid_filter",
            "message": f"{name} must include a timezone offset"})
    return parsed.astimezone(timezone.utc).isoformat()


def add_usage_routes(app, router, db, ctx) -> None:
    """Attach /api/v1/usage/* routes to the P0 application factory."""

    @router.post("/usage/events", response_model=UsageEventResponse,
                 status_code=201)
    def create_usage_event(payload: UsageEventClaim, response: Response):
        try:
            result = ingest_usage_event(db, context=ctx, claim=payload)
        except TenantViolation:
            # 404 hidden: never reveal whether the device exists elsewhere.
            raise HTTPException(status_code=404, detail="not found")
        except IngestConflict as exc:
            raise HTTPException(status_code=409, detail={
                "error": "usage_conflict",
                "message": "source_event_id already exists with "
                           "different immutable facts"})
        if result.status == "duplicate":
            # spec section 10: duplicate -> 200, not 409
            response.status_code = 200
        return _event_response(result.event)

    @router.post("/usage/events:batch", response_model=UsageBatchResponse)
    async def create_usage_event_batch(request: Request):
        # Size gate BEFORE parsing: oversize bodies are rejected whole.
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > _MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail={
                "error": "body_too_large",
                "message": "batch body exceeds 1 MiB"})
        raw = await request.body()
        if len(raw) > _MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail={
                "error": "body_too_large",
                "message": "batch body exceeds 1 MiB"})
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            # Whole-request schema failure -> 422, zero writes.
            raise HTTPException(status_code=422, detail={
                "error": "malformed_json",
                "message": "request body is not valid JSON"}) from exc
        try:
            batch = UsageEventBatchRequest.model_validate(data)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail={
                "error": "batch_schema",
                "message": "request envelope invalid (max "
                           f"{_MAX_BATCH_ITEMS} events, whitelist fields "
                           "only)"}) from exc

        # Per-item results; every item owns its ingest transaction, so a
        # rejected item never rolls back accepted siblings.
        results: list[UsageBatchItemResult] = []
        for item in batch.events:
            try:
                result = ingest_usage_event(db, context=ctx, claim=item)
            except TenantViolation:
                results.append(UsageBatchItemResult(
                    status="rejected", detail="device not found"))
            except IngestConflict:
                results.append(UsageBatchItemResult(
                    status="rejected",
                    detail="source_event_id conflicts with an existing "
                           "event"))
            except ValidationError:
                results.append(UsageBatchItemResult(
                    status="rejected", detail="schema validation failed"))
            else:
                results.append(UsageBatchItemResult(
                    status=result.status, event_id=result.event.id))
        return UsageBatchResponse(results=results)

    @router.get("/usage/events/{event_id}",
                response_model=UsageEventResponse)
    def get_usage_event(event_id: str):
        row = db.execute(
            "SELECT " + ",".join(_SELECT_COLUMNS) +
            " FROM usage_events WHERE id = ? AND organization_id = ?",
            (event_id, ctx.organization_id),
        ).fetchone()
        if row is None:
            # Hidden for foreign tenants and unknown ids alike.
            raise HTTPException(status_code=404, detail="not found")
        return _row_response(row)

    @router.get("/usage/events", response_model=list[UsageEventResponse])
    def list_usage_events(
        from_at: Optional[str] = Query(default=None, alias="from"),
        to_at: Optional[str] = Query(default=None, alias="to"),
        device_id: Optional[str] = Query(default=None),
        member_id: Optional[str] = Query(default=None),
        provider: Optional[str] = Query(default=None),
    ):
        where = ["organization_id = ?"]
        params: list = [ctx.organization_id]
        bound_from = _parse_bound(from_at, "from")
        if bound_from is not None:
            where.append("started_at >= ?")
            params.append(bound_from)
        bound_to = _parse_bound(to_at, "to")
        if bound_to is not None:
            where.append("started_at <= ?")
            params.append(bound_to)
        if device_id:
            where.append("device_id = ?")
            params.append(device_id)
        if member_id:
            where.append("member_id = ?")
            params.append(member_id)
        if provider:
            # Stored providers are lowercase (ingest normalizes); the
            # filter is normalized to match, never to widen authority.
            where.append("provider = ?")
            params.append(provider.strip().lower())
        rows = db.execute(
            "SELECT " + ",".join(_SELECT_COLUMNS) +
            " FROM usage_events WHERE " + " AND ".join(where) +
            " ORDER BY started_at, id",
            tuple(params),
        ).fetchall()
        return [_row_response(row) for row in rows]
