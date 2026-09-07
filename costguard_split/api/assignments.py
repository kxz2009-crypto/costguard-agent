"""P0-06 manual deterministic device assignment (server side).

MANUAL only: the caller names the member; the server enforces the
timeline. No automatic inference / confidence / behavior model exists
anywhere in this module (a test asserts their absence).

Rules:
- close-old + insert-new happen in reassign_device's SINGLE transaction;
  an insert failure rolls the close back too (no attribution gap).
- P0 API policy on explicit timestamps (prevents silent rewrite of
  current attribution; a backdated CORRECTION of a live assignment is a
  separate future endpoint):
    * device has NO open assignment -> explicit valid_from allowed
      (first assignment), validated against closed history (no overlap).
    * device HAS an open assignment -> effective_at must be >= server
      now; a backdated reassignment would truncate the live interval and
      silently rewrite attribution for the covered period -> 409.
- disabled members cannot receive new assignments.
- audit: device.assignment_created / device.reassigned with before/after
  (member ids only — never raw evidence), reason, org, timestamp.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from ..services.device_registry import (
    OverlappingAssignment, current_member, enroll_assignment,
    reassign_device,
)
from .context import ServerContext, assert_tenant
from .members import _member_row


class AssignmentConflict(Exception):
    """Timeline/state conflict (overlap, disabled member, backdate of a
    live assignment) -> HTTP 409."""


def _now() -> datetime:
    """Return one timezone-aware canonical UTC server instant."""
    return datetime.now(timezone.utc)


def _parse_utc(value: str) -> datetime:
    """Parse an ISO timestamp and normalize it to an aware UTC datetime."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("valid_from must include a timezone offset")
    return parsed.astimezone(timezone.utc)


def create_assignment_api(db, *, context: ServerContext, device_id: str,
                          member_id: str, valid_from: Optional[str] = None,
                          reason: Optional[str] = None) -> dict:
    """Assign device -> member (manual, deterministic)."""
    org = context.organization_id
    server_now = _now()
    try:
        effective_at = (_parse_utc(valid_from) if valid_from is not None
                        else server_now)
    except ValueError as exc:
        raise AssignmentConflict("valid_from must be a timezone-aware ISO "
                                 "timestamp") from exc
    effective = effective_at.isoformat()

    # tenant gates (foreign ids are 404-hidden)
    assert_tenant(db, "devices", organization_id=org, row_id=device_id)
    member = _member_row(db, org, member_id)
    if member[4] == "disabled":
        raise AssignmentConflict(
            "member is disabled and cannot receive a new assignment")

    has_open = current_member(db, device_id) is not None
    if has_open and effective_at < server_now:
        raise AssignmentConflict(
            "backdated reassignment of a live assignment is not allowed "
            "through this endpoint (attribution rewrite); pass a current "
            "or future effective time")

    try:
        if has_open:
            _, new = reassign_device(
                db, organization_id=org, device_id=device_id,
                new_member_id=member_id, effective_at=effective,
                assigned_by=context.actor_id, reason=reason)
            result = new
        else:
            result = enroll_assignment(
                db, organization_id=org, device_id=device_id,
                member_id=member_id, valid_from=effective,
                assigned_by=context.actor_id, reason=reason)
    except OverlappingAssignment as exc:
        db.rollback()
        raise AssignmentConflict(str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise AssignmentConflict(str(exc)) from exc
    return {"assignment_id": result.id, "device_id": device_id,
            "member_id": member_id, "valid_from": result.valid_from,
            "valid_to": result.valid_to, "reason": result.reason,
            "created_at": result.created_at}
