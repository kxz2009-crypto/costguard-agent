"""Append-only audit writer (PATCH 8 hardened).

Rules:
- before_json / after_json are ALWAYS structured JSON payloads produced
  by json.dumps here — callers pass dicts, never pre-formatted strings,
  never repr() output. PostgreSQL mapping: JSONB.
- Append-only: this module exposes record() and readers ONLY. There is
  intentionally no update_audit / delete_audit function anywhere in the
  Split codebase; a test asserts their absence.
- organization_id is mandatory — every audit row is tenant-scoped.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def record(db, *, organization_id: str, event_type: str,
           entity_type: str, entity_id: str,
           before: Optional[dict[str, Any]] = None,
           after: Optional[dict[str, Any]] = None,
           actor_id: Optional[str] = None,
           reason: Optional[str] = None) -> str:
    """Insert one audit_events row. before/after MUST be dict/None;
    serialization happens here (single serializer, JSON objects only)."""
    if before is not None and not isinstance(before, dict):
        raise TypeError("audit before must be a dict or None")
    if after is not None and not isinstance(after, dict):
        raise TypeError("audit after must be a dict or None")
    if not organization_id:
        raise ValueError("audit events require organization_id")
    event_id = "aud_" + uuid4().hex
    db.execute(
        "INSERT INTO audit_events (id, organization_id, actor_id,"
        " event_type, entity_type, entity_id, before_json, after_json,"
        " reason, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (event_id, organization_id, actor_id, event_type, entity_type,
         entity_id,
         json.dumps(before, ensure_ascii=False, sort_keys=True)
         if before is not None else None,
         json.dumps(after, ensure_ascii=False, sort_keys=True)
         if after is not None else None,
         reason, _now_iso()))
    return event_id


def list_for_entity(db, *, organization_id: str, entity_id: str):
    """Reader: audit rows for one entity, oldest first (append-only)."""
    return db.execute(
        "SELECT id, event_type, entity_type, entity_id, before_json,"
        " after_json, actor_id, reason, created_at FROM audit_events"
        " WHERE organization_id = ? AND entity_id = ?"
        " ORDER BY created_at, id", (organization_id, entity_id))
