"""P0-04 device registration service (server side of the trust boundary).

Semantics (spec P0-04):
- Idempotent on (organization_id, device_uid): first call creates, later
  calls refresh mutable evidence + server-side last_seen and return the
  SAME server device identity with created=False.
- device_uid is globally unique: registering an existing uid under a
  DIFFERENT organization raises RegistrationConflict (HTTP 409) and writes
  a security audit event. Never silent adopt / transfer / duplicate.
- New devices are NOT membered: assignment_status is DERIVED (no open
  device_assignment row) — lifecycle status stays 'active'.
- All canonical timestamps are server-side (datetime.now(UTC)); client
  observation times are not accepted at this boundary at all (P0 keeps
  the payload minimal).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from ..services import audit
from ..services.device_registry import register_device, current_member
from .context import ServerContext, TenantViolation, assert_tenant
from .schemas import DeviceRegisterRequest  # noqa: F401 (type re-export)


class RegistrationConflict(Exception):
    """device_uid already belongs to a DIFFERENT organization."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def register_device_api(db: sqlite3.Connection, *, context: ServerContext,
                        device_uid: str, hostname_fingerprint: str,
                        username_fingerprint: str,
                        network_fingerprint: Optional[str],
                        os_name: str, arch: str,
                        collector_version: str) -> tuple[dict, bool]:
    """Register (or re-observe) a device. Returns (response_dict, created).

    Trust boundary: organization comes from `context`, never from payload.
    """
    org = context.organization_id
    now = _now()

    # Global-unique check FIRST: a uid owned by another org is a hard 409
    # with a security audit event, never a silent adopt/transfer.
    row = db.execute(
        "SELECT id, organization_id FROM devices WHERE device_uid = ?",
        (device_uid,)).fetchone()
    if row is not None and row[1] != org:
        audit.record(db, organization_id=org,
                     event_type="device.registration_rejected",
                     entity_type="device", entity_id=row[0],
                     before=None,
                     after={"device_uid": device_uid,
                            "owner_organization_id": row[1]},
                     actor_id=context.actor_id,
                     reason="cross-org device_uid collision rejected")
        db.commit()
        raise RegistrationConflict(
            f"device_uid already registered to another organization")

    device, created = register_device(
        db, organization_id=org, device_uid=device_uid,
        display_name=f"device-{device_uid[-8:]}",
        hostname_hash=hostname_fingerprint,
        username_hash=username_fingerprint,
        os_name=os_name, arch=arch,
        first_seen_at=now,                    # server time is canonical
        collector_version=collector_version,
        network_hash=network_fingerprint,
        actor_id=context.actor_id)

    assigned = current_member(db, device.id) is not None
    response = {
        "device_id": device.id,
        "device_uid": device.device_uid,
        "status": device.status,
        "assignment_status": "assigned" if assigned else "unassigned",
        "first_seen_at": device.first_seen_at,
        "last_seen_at": device.last_seen_at,
    }
    return response, created


def get_device_api(db: sqlite3.Connection, *, context: ServerContext,
                   device_id: str) -> dict:
    """Fetch one device inside the caller's organization. Foreign-tenant
    ids raise TenantViolation -> 404 (hidden, not 403: no enumeration)."""
    assert_tenant(db, "devices", organization_id=context.organization_id,
                  row_id=device_id)
    row = db.execute(
        "SELECT id, device_uid, status, first_seen_at, last_seen_at"
        " FROM devices WHERE id = ?", (device_id,)).fetchone()
    assigned = current_member(db, device_id) is not None
    return {
        "device_id": row[0],
        "device_uid": row[1],
        "status": row[2],
        "assignment_status": "assigned" if assigned else "unassigned",
        "first_seen_at": row[3],
        "last_seen_at": row[4],
    }
