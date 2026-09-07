"""P1A-03 tenant-safe, idempotent usage ingestion service.

One transaction owns device resolution, event-time assignment lookup,
idempotency decision, usage insertion, and audit insertion. Collector claims
never supply server authority or money fields.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from ..api.context import ServerContext, TenantViolation
from ..models.usage import UsageEvent
from ..schemas.dto import canonical_source_event_id
from ..schemas.usage import UsageEventClaim
from ..services import audit
from ..services.device_registry import member_at
from .pricing_public import estimate_cost


class IngestConflict(ValueError):
    """An existing event identity has different immutable claim facts."""


@dataclass(frozen=True)
class IngestResult:
    status: str  # created | duplicate
    event: UsageEvent


_EVENT_COLUMNS = (
    "id", "organization_id", "device_id", "device_uid", "member_id",
    "provider", "provider_account_ref", "model", "session_ref",
    "source_event_id", "started_at", "ended_at", "received_at",
    "input_tokens", "cached_input_tokens", "cache_write_tokens",
    "output_tokens", "reasoning_tokens", "request_count", "pricing_version",
    "api_equivalent_cost_usd", "source_type", "collector_version",
    "created_at",
)
_SELECT_EVENT = "SELECT " + ",".join(_EVENT_COLUMNS) + " FROM usage_events"

# These are the collector-owned immutable facts. Server-derived member and
# timestamps are deliberately excluded from duplicate equality checks.
_CLAIM_FACT_COLUMNS = (
    "device_uid", "provider", "provider_account_ref", "model", "session_ref",
    "source_event_id", "started_at", "ended_at", "input_tokens",
    "cached_input_tokens", "cache_write_tokens", "output_tokens",
    "reasoning_tokens", "request_count", "source_type", "collector_version",
)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _normalized_provider(value: str) -> str:
    return value.strip().lower()


def _source_event_id(claim: UsageEventClaim, provider: str,
                     started_at: str, ended_at: str) -> str:
    if claim.source_event_id is not None:
        value = claim.source_event_id.strip()
        prefix = provider + ":"
        return value if value.startswith(prefix) else canonical_source_event_id(
            provider, value)
    native_material = "|".join((
        provider,
        claim.session_ref,
        started_at,
        ended_at,
        claim.model,
        str(claim.input_tokens),
        str(claim.cached_input_tokens),
        str(claim.cache_write_tokens),
        str(claim.output_tokens),
        str(claim.reasoning_tokens),
        str(claim.request_count),
    ))
    native = hashlib.sha256(native_material.encode("utf-8")).hexdigest()[:32]
    return canonical_source_event_id(provider, native)


def _event_from_row(row) -> UsageEvent:
    return UsageEvent(**dict(zip(_EVENT_COLUMNS, row)))


def _claim_facts(event: UsageEvent) -> tuple:
    return tuple(getattr(event, name) for name in _CLAIM_FACT_COLUMNS)


def _safe_audit_after(event: UsageEvent) -> dict:
    """Allowlisted audit projection: identifiers and token counts only."""
    return {
        "usage_event_id": event.id,
        "device_id": event.device_id,
        "member_id": event.member_id,
        "provider": event.provider,
        "source_event_id": event.source_event_id,
        "started_at": event.started_at,
        "ended_at": event.ended_at,
        "input_tokens": event.input_tokens,
        "cached_input_tokens": event.cached_input_tokens,
        "cache_write_tokens": event.cache_write_tokens,
        "output_tokens": event.output_tokens,
        "reasoning_tokens": event.reasoning_tokens,
        "request_count": event.request_count,
    }


def _record_rejection(db, *, context: ServerContext, entity_id: str,
                      provider: str, reason: str) -> None:
    audit.record(
        db,
        organization_id=context.organization_id,
        event_type="usage.rejected",
        entity_type="usage_event",
        entity_id=entity_id,
        before=None,
        after={"provider": provider, "source_event_id": entity_id},
        actor_id=context.actor_id,
        reason=reason,
    )


def ingest_usage_event(db, *, context: ServerContext,
                       claim: UsageEventClaim) -> IngestResult:
    """Validate resolved authority and atomically ingest one usage claim.

    Expected rejections are audited and committed without a usage mutation;
    unexpected failures roll back both usage and audit writes.
    """
    org = context.organization_id
    provider = _normalized_provider(claim.provider)
    started_at = _iso_utc(claim.started_at)
    ended_at = _iso_utc(claim.ended_at)
    source_event_id = _source_event_id(
        claim, provider, started_at, ended_at)
    now = datetime.now(timezone.utc).isoformat()
    event_id = "uev_" + uuid4().hex

    try:
        # Acquire the SQLite write reservation before the identity lookup so
        # concurrent retries serialize around lookup -> insert -> audit.
        db.execute("BEGIN IMMEDIATE")
        device = db.execute(
            "SELECT id FROM devices WHERE organization_id=? AND device_uid=?",
            (org, claim.device_uid),
        ).fetchone()
        if device is None:
            _record_rejection(
                db, context=context, entity_id=source_event_id,
                provider=provider, reason="device not found in organization")
            db.commit()
            raise TenantViolation("device not found")
        device_id = device[0]
        member_id = member_at(db, device_id=device_id, at=started_at)

        # P1A-09: optional public price estimation, CREATED path only.
        # Default OFF -> (None, None); duplicates/rejections never reach
        # this recompute and stored money is never mutated afterwards.
        # estimate_cost is fail-open to (None, None) on any table/price
        # problem and never raises.
        pricing_version, api_cost = estimate_cost(claim)

        candidate = UsageEvent(
            id=event_id,
            organization_id=org,
            device_id=device_id,
            device_uid=claim.device_uid,
            member_id=member_id,
            provider=provider,
            provider_account_ref=claim.provider_account_ref,
            model=claim.model,
            session_ref=claim.session_ref,
            source_event_id=source_event_id,
            started_at=started_at,
            ended_at=ended_at,
            received_at=now,
            input_tokens=claim.input_tokens,
            cached_input_tokens=claim.cached_input_tokens,
            cache_write_tokens=claim.cache_write_tokens,
            output_tokens=claim.output_tokens,
            reasoning_tokens=claim.reasoning_tokens,
            request_count=claim.request_count,
            pricing_version=pricing_version,
            api_equivalent_cost_usd=api_cost,
            source_type=claim.source_type,
            collector_version=claim.collector_version,
            created_at=now,
        )

        existing_row = db.execute(
            _SELECT_EVENT + " WHERE organization_id=? AND device_uid=? "
            "AND provider=? AND source_event_id=?",
            (org, claim.device_uid, provider, source_event_id),
        ).fetchone()
        if existing_row is not None:
            existing = _event_from_row(existing_row)
            if _claim_facts(existing) != _claim_facts(candidate):
                _record_rejection(
                    db, context=context, entity_id=existing.id,
                    provider=provider,
                    reason="source_event_id conflicts with immutable facts")
                db.commit()
                raise IngestConflict(
                    "source_event_id already exists with different payload")
            audit.record(
                db, organization_id=org, event_type="usage.duplicate",
                entity_type="usage_event", entity_id=existing.id,
                before=None,
                after={"provider": provider,
                       "source_event_id": source_event_id},
                actor_id=context.actor_id,
                reason="identical idempotent retransmit")
            db.commit()
            return IngestResult("duplicate", existing)

        placeholders = ",".join("?" for _ in _EVENT_COLUMNS)
        db.execute(
            f"INSERT INTO usage_events ({','.join(_EVENT_COLUMNS)}) "
            f"VALUES ({placeholders})",
            tuple(getattr(candidate, name) for name in _EVENT_COLUMNS),
        )
        audit.record(
            db, organization_id=org, event_type="usage.ingested",
            entity_type="usage_event", entity_id=candidate.id,
            before=None, after=_safe_audit_after(candidate),
            actor_id=context.actor_id, reason="usage claim accepted")
        db.commit()
        return IngestResult("created", candidate)
    except (TenantViolation, IngestConflict):
        if db.in_transaction:
            db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
