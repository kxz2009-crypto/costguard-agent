"""P0-05 Member CRUD (server side).

Member rules (spec P0-05):
- fields: id, display_name, email_optional, status(active|disabled), times
- NO hard delete exists anywhere in this module (a disabled member that
  participates in assignment history must remain resolvable).
- Every read/mutation goes through assert_tenant: a foreign member id is
  indistinguishable from a nonexistent one (TenantViolation -> 404).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from ..services import audit
from .context import ServerContext, TenantViolation, assert_tenant


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# P0-05 member CRUD
# ---------------------------------------------------------------------------

def create_member_api(db, *, context: ServerContext, display_name: str,
                      email_optional: Optional[str]) -> dict:
    member_id = "mem_" + uuid4().hex
    now = _now()
    db.execute(
        "INSERT INTO members (id, organization_id, display_name,"
        " email_optional, status, created_at, updated_at)"
        " VALUES (?,?,?,?, 'active', ?, ?)",
        (member_id, context.organization_id, display_name,
         email_optional, now, now))
    audit.record(db, organization_id=context.organization_id,
                 event_type="member.created", entity_type="member",
                 entity_id=member_id, before=None,
                 after={"display_name": display_name,
                        "email_optional": email_optional,
                        "status": "active"},
                 actor_id=context.actor_id, reason=None)
    db.commit()
    return get_member_api(db, context=context, member_id=member_id)


def _member_row(db, organization_id: str, member_id: str):
    assert_tenant(db, "members", organization_id=organization_id,
                  row_id=member_id)
    return db.execute(
        "SELECT id, organization_id, display_name, email_optional, status,"
        " created_at, updated_at FROM members WHERE id = ?",
        (member_id,)).fetchone()


def get_member_api(db, *, context: ServerContext, member_id: str) -> dict:
    r = _member_row(db, context.organization_id, member_id)
    return {"member_id": r[0], "organization_id": r[1],
            "display_name": r[2], "email_optional": r[3], "status": r[4],
            "created_at": r[5], "updated_at": r[6]}


def list_members_api(db, *, context: ServerContext) -> list[dict]:
    rows = db.execute(
        "SELECT id, organization_id, display_name, email_optional, status,"
        " created_at, updated_at FROM members WHERE organization_id = ?"
        " ORDER BY created_at, id", (context.organization_id,)).fetchall()
    return [{"member_id": r[0], "organization_id": r[1],
             "display_name": r[2], "email_optional": r[3], "status": r[4],
             "created_at": r[5], "updated_at": r[6]} for r in rows]


def update_member_api(db, *, context: ServerContext, member_id: str,
                      display_name: Optional[str] = None,
                      email_optional: Optional[str] = None,
                      status: Optional[str] = None) -> dict:
    current = _member_row(db, context.organization_id, member_id)
    new_name = current[2] if display_name is None else display_name
    new_email = current[3] if email_optional is None else email_optional
    new_status = current[4] if status is None else status
    now = _now()
    db.execute(
        "UPDATE members SET display_name = ?, email_optional = ?,"
        " status = ?, updated_at = ? WHERE id = ? AND organization_id = ?",
        (new_name, new_email, new_status, now, member_id,
         context.organization_id))
    audit.record(db, organization_id=context.organization_id,
                 event_type=("member.disabled" if status == "disabled"
                             else "member.updated"),
                 entity_type="member", entity_id=member_id,
                 before={"display_name": current[2],
                         "email_optional": current[3],
                         "status": current[4]},
                 after={"display_name": new_name,
                        "email_optional": new_email,
                        "status": new_status},
                 actor_id=context.actor_id, reason=None)
    db.commit()
    return get_member_api(db, context=context, member_id=member_id)


