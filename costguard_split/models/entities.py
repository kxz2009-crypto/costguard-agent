"""Split P0 entity dataclasses — the domain layer (storage-agnostic)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

DEVICE_STATUSES = ("active", "disabled", "retired")
MEMBER_STATUSES = ("active", "disabled")


@dataclass
class Organization:
    id: str
    name: str
    status: str = "active"
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Member:
    id: str
    organization_id: str
    display_name: str
    email_optional: Optional[str] = None
    status: str = "active"
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Device:
    """Lifecycle entity. Membership is DERIVED from device_assignments
    (PATCH 6) — there is intentionally no persisted member_id here.
    `status` is lifecycle-only: active | disabled | retired."""
    id: str
    organization_id: str
    device_uid: str
    display_name: str
    hostname_hash: str
    username_hash: str
    os: str
    arch: str
    first_seen_at: str
    last_seen_at: str
    last_network_hash: Optional[str] = None
    status: str = "active"
    identity_confidence: int = 0
    collector_version: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if self.status not in DEVICE_STATUSES:
            raise ValueError(f"invalid device status: {self.status!r}")


@dataclass
class AuditEvent:
    id: str
    organization_id: str
    event_type: str
    entity_type: str
    entity_id: str
    actor_id: Optional[str] = None
    before_json: Optional[str] = None
    after_json: Optional[str] = None
    reason: Optional[str] = None
    created_at: str = ""
