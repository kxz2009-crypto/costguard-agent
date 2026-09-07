"""Device registry service — the ONLY way devices enter the Split DB.

Hardened invariants (PATCH 4/5/6):
- register_device is idempotent on device_uid; new devices get
  status='active' (lifecycle) and NO member — membership is DERIVED from
  device_assignments (PATCH 6: no member_id column, no 'unassigned'
  lifecycle value; "unassigned" == no row with valid_to IS NULL).
- enroll_assignment / reassign write the bitemporal timeline (PATCH 5):
  one open-ended row per device max; overlap is impossible — SQLite has
  no EXCLUDE constraint, so this is DB FK/UNIQUE + transaction guard +
  tests (documented SQLite limitation; on PostgreSQL it becomes a GiST
  EXCLUDE constraint with the same semantics).
- every state transition writes an audit event (PATCH 8: structured
  before/after JSON only).
- cross-org references are rejected by composite FKs; tests prove it.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from ..models.entities import Device
from . import audit

LIFECYCLE_STATUSES = ("active", "disabled", "retired")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _device_from_row(row) -> Device:
    return Device(
        id=row[0], organization_id=row[1], device_uid=row[2],
        display_name=row[3], hostname_hash=row[4],
        username_hash=row[5], os=row[6], arch=row[7],
        first_seen_at=row[8], last_seen_at=row[9],
        last_network_hash=row[10], status=row[11],
        identity_confidence=row[12], collector_version=row[13],
        created_at=row[14], updated_at=row[15])


_SELECT = ("SELECT id, organization_id, device_uid, display_name,"
           " hostname_hash, username_hash, os, arch, first_seen_at,"
           " last_seen_at, last_network_hash, status, identity_confidence,"
           " collector_version, created_at, updated_at FROM devices")


def register_device(db: sqlite3.Connection, *, organization_id: str,
                    device_uid: str, display_name: str,
                    hostname_hash: str, username_hash: str,
                    os_name: str, arch: str,
                    first_seen_at: str,
                    collector_version: str = "",
                    network_hash: Optional[str] = None,
                    actor_id: Optional[str] = None) -> tuple[Device, bool]:
    """Idempotent on device_uid. Returns (device, created).

    created=True  -> lifecycle 'active', NO member (derived unassigned).
    created=False -> refresh last_seen/last_network only; lifecycle and
                     membership are untouched.
    """
    from ..identity.device_uid import parse_device_uid
    parse_device_uid(device_uid)          # single validation source
    now = _now_iso()
    row = db.execute(
        "SELECT id FROM devices WHERE device_uid = ?", (device_uid,)).fetchone()
    if row:
        dev_id = row[0]
        before = db.execute(
            "SELECT last_seen_at, last_network_hash FROM devices"
            " WHERE id = ?", (dev_id,)).fetchone()
        new_net = network_hash if network_hash is not None else before[1]
        db.execute(
            "UPDATE devices SET last_seen_at = ?, last_network_hash = ?,"
            " updated_at = ? WHERE id = ?", (now, new_net, now, dev_id))
        audit.record(db, organization_id=organization_id,
                     event_type="device.seen", entity_type="device",
                     entity_id=dev_id,
                     before={"last_seen_at": before[0],
                             "last_network_hash": before[1]},
                     after={"last_seen_at": now, "last_network_hash": new_net},
                     actor_id=actor_id,
                     reason="re-registration (idempotent)")
        db.commit()
        return _device_from_row(db.execute(
            _SELECT + " WHERE id = ?", (dev_id,)).fetchone()), False

    dev_id = "dev_" + uuid4().hex
    db.execute(
        "INSERT INTO devices (id, organization_id, device_uid,"
        " display_name, hostname_hash, username_hash, os, arch,"
        " first_seen_at, last_seen_at, last_network_hash, status,"
        " identity_confidence, collector_version, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?, 'active', 0, ?,?,?)",
        (dev_id, organization_id, device_uid, display_name,
         hostname_hash, username_hash, os_name, arch,
         first_seen_at, now, network_hash, collector_version, now, now))
    audit.record(db, organization_id=organization_id,
                 event_type="device.registered", entity_type="device",
                 entity_id=dev_id, before=None,
                 after={"device_uid": device_uid, "status": "active",
                        "display_name": display_name,
                        "member": None},
                 actor_id=actor_id,
                 reason="first registration; membership derived empty")
    db.commit()
    return _device_from_row(db.execute(
        _SELECT + " WHERE id = ?", (dev_id,)).fetchone()), True


def get_by_uid(db: sqlite3.Connection, device_uid: str) -> Optional[Device]:
    row = db.execute(_SELECT + " WHERE device_uid = ?",
                     (device_uid,)).fetchone()
    return _device_from_row(row) if row else None


# ---------------------------------------------------------------------------
# PATCH 5/6: assignment timeline primitives (schema-level; the P0-06 API
# and UI come later — these are the only sanctioned mutation paths).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Assignment:
    id: str
    organization_id: str
    device_id: str
    member_id: str
    valid_from: str
    valid_to: Optional[str]
    assigned_by: Optional[str]
    reason: Optional[str]
    created_at: str


_ASG_SELECT = ("SELECT id, organization_id, device_id, member_id,"
               " valid_from, valid_to, assigned_by, reason, created_at"
               " FROM device_assignments")


def _asg_from_row(row) -> Assignment:
    return Assignment(*row)


def _assert_open_interval_bounds(db, organization_id: str, device_id: str,
                                 valid_from: str,
                                 valid_to: Optional[str]) -> None:
    """Transaction-level overlap guard (SQLite has no EXCLUDE constraint).

    Semantics: at most ONE open-ended (valid_to IS NULL) assignment per
    device; closed intervals must not overlap any existing interval.
    PostgreSQL migration note: replace with
        EXCLUDE USING gist (device_id WITH =, tstzrange(valid_from,
        valid_to) WITH &&)
    — same rule, enforced by the database.
    """
    if valid_to is not None and valid_to <= valid_from:
        raise ValueError("valid_to must be after valid_from")
    open_row = db.execute(
        "SELECT id FROM device_assignments WHERE device_id = ?"
        " AND valid_to IS NULL", (device_id,)).fetchone()
    if valid_to is None and open_row:
        raise OverlappingAssignment(
            f"device {device_id} already has an open assignment"
            f" ({open_row[0]}); close it first (reassign)")
    if valid_to is not None:
        clash = db.execute(
            "SELECT id FROM device_assignments WHERE device_id = ? AND ("
            " (valid_to IS NULL)"
            " OR (valid_from < ? AND (valid_to IS NULL OR valid_to > ?)))",
            (device_id, valid_to, valid_from)).fetchone()
        if clash:
            raise OverlappingAssignment(
                f"proposed interval overlaps assignment {clash[0]}")


class OverlappingAssignment(ValueError):
    pass


def enroll_assignment(db: sqlite3.Connection, *, organization_id: str,
                      device_id: str, member_id: str,
                      valid_from: str,
                      valid_to: Optional[str] = None,
                      assigned_by: Optional[str] = None,
                      reason: Optional[str] = None) -> Assignment:
    """Insert one timeline row. Device must be member-less right now
    (no open assignment) — enforced by _assert_open_interval_bounds."""
    asg_id = "asg_" + uuid4().hex
    try:
        db.execute("BEGIN")
        # tenant-safe existence checks (FK would also catch; these give
        # better errors and keep the guard explicit)
        if not db.execute(
                "SELECT 1 FROM devices WHERE id=? AND organization_id=?",
                (device_id, organization_id)).fetchone():
            raise ValueError(f"device {device_id} not in org {organization_id}")
        if not db.execute(
                "SELECT 1 FROM members WHERE id=? AND organization_id=?",
                (member_id, organization_id)).fetchone():
            raise ValueError(f"member {member_id} not in org {organization_id}")
        _assert_open_interval_bounds(db, organization_id, device_id,
                                     valid_from, valid_to)
        now = _now_iso()
        db.execute(
            "INSERT INTO device_assignments (id, organization_id,"
            " device_id, member_id, valid_from, valid_to, assigned_by,"
            " reason, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (asg_id, organization_id, device_id, member_id, valid_from,
             valid_to, assigned_by, reason, now))
        audit.record(db, organization_id=organization_id,
                     event_type="device.assignment_created",
                     entity_type="device_assignment", entity_id=asg_id,
                     before={"member": None},
                     after={"member": member_id, "device": device_id,
                            "valid_from": valid_from, "valid_to": valid_to},
                     actor_id=assigned_by, reason=reason)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return _asg_from_row(db.execute(
        _ASG_SELECT + " WHERE id = ?", (asg_id,)).fetchone())


def reassign_device(db: sqlite3.Connection, *, organization_id: str,
                    device_id: str, new_member_id: str,
                    effective_at: str,
                    assigned_by: Optional[str] = None,
                    reason: Optional[str] = None) -> tuple[Assignment,
                                                           Assignment]:
    """Close the open assignment at effective_at and open a new one for
    the new member. History is never deleted. One transaction = one
    atomic owner change."""
    try:
        db.execute("BEGIN")
        old = db.execute(
            _ASG_SELECT + " WHERE device_id = ? AND valid_to IS NULL",
            (device_id,)).fetchone()
        if not old:
            raise ValueError(f"device {device_id} has no open assignment")
        old = _asg_from_row(old)
        if old.member_id == new_member_id:
            raise ValueError("new member equals current member")
        if effective_at <= old.valid_from:
            raise ValueError("effective_at must be after current valid_from")
        db.execute(
            "UPDATE device_assignments SET valid_to = ? WHERE id = ?",
            (effective_at, old.id))
        asg_id = "asg_" + uuid4().hex
        now = _now_iso()
        db.execute(
            "INSERT INTO device_assignments (id, organization_id,"
            " device_id, member_id, valid_from, valid_to, assigned_by,"
            " reason, created_at) VALUES (?,?,?,?,?,NULL,?,?,?)",
            (asg_id, organization_id, device_id, new_member_id,
             effective_at, assigned_by, reason, now))
        audit.record(db, organization_id=organization_id,
                     event_type="device.reassigned", entity_type="device",
                     entity_id=device_id,
                     before={"member": old.member_id,
                             "assignment": old.id},
                     after={"member": new_member_id, "assignment": asg_id,
                            "effective_at": effective_at},
                     actor_id=assigned_by, reason=reason)
        db.commit()
    except Exception:
        db.rollback()
        raise
    new_row = db.execute(_ASG_SELECT + " WHERE id = ?",
                         (asg_id,)).fetchone()
    return old, _asg_from_row(new_row)


def member_at(db: sqlite3.Connection, *, device_id: str,
              at: str) -> Optional[str]:
    """Event-time attribution helper (PATCH 5 core): the member whose
    assignment interval contains `at`. NULL => unassigned at that time.
    Usage attribution must call THIS, never read a current-owner column."""
    row = db.execute(
        "SELECT member_id FROM device_assignments WHERE device_id = ?"
        " AND valid_from <= ? AND (valid_to IS NULL OR valid_to > ?)"
        " ORDER BY valid_from DESC LIMIT 1", (device_id, at, at)).fetchone()
    return row[0] if row else None


def current_member(db: sqlite3.Connection, device_id: str) -> Optional[str]:
    """Derived current owner (open-ended row) — a VIEW over the timeline."""
    row = db.execute(
        "SELECT member_id FROM device_assignments WHERE device_id = ?"
        " AND valid_to IS NULL", (device_id,)).fetchone()
    return row[0] if row else None
