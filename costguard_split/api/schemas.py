"""P0-04/05/06 API-layer DTOs — strict trust-boundary contracts.

Layering rule: the domain/service layer (costguard_split.services) NEVER
imports this module; the HTTP layer converts these DTOs into service calls.
The core package therefore stays zero-dependency; this module requires
pydantic only (an optional [split-server] extra).

Trust boundary (spec P0-04):
- Client MAY CLAIM: device_uid + safe fingerprints (hk1:...) + os/arch +
  collector_version. NOTHING else.
- Server DETERMINES: organization (request context), member attribution,
  timestamps, identity_confidence, pricing/cost/allocation.
- Forbidden-authority and raw fields are REJECTED (4xx), never silently
  ignored, so the wire contract stays explicit.
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

# hk1:<32 hex> — the ONLY accepted fingerprint shape. Raw hostname /
# username / IP can never enter through the API; hashing happens on the
# trusted collector side, never at this boundary.
_HK1_RE = re.compile(r"^hk1:[0-9a-f]{32}$")

# The canonical collector wire shape (P1A-02). The batch envelope and the
# usage routes reuse it verbatim: claims, never server models.
from ..schemas.usage import UsageEventClaim  # noqa: E402

# Forbidden in ANY registration payload — either authority the client must
# not claim, or raw evidence the protocol must never see.
FORBIDDEN_AUTHORITY_FIELDS = (
    "organization_id", "member_id", "identity_confidence",
    "cost", "price", "allocation", "api_equivalent_cost",
    "estimated_cost", "billing",
)
FORBIDDEN_RAW_FIELDS = (
    "hostname", "username", "raw_ip", "ip", "public_ip", "local_ip",
    "network", "device", "device_json", "metadata",
)
ALL_FORBIDDEN = FORBIDDEN_AUTHORITY_FIELDS + FORBIDDEN_RAW_FIELDS


def _reject_forbidden(payload: dict) -> None:
    present = sorted(set(payload) & set(ALL_FORBIDDEN))
    if present:
        raise ValueError(
            f"forbidden field(s) {present}: clients may not submit authority "
            f"or raw-evidence fields; the API accepts whitelisted safe "
            f"evidence only")


def _validate_uid(value: str) -> str:
    from ..identity.device_uid import validate_device_uid
    if not validate_device_uid(value):
        raise ValueError("device_uid must be canonical cgdev_<uuid> "
                         "(lowercase, hyphenated)")
    return value


def _validate_hk1(value: Optional[str]) -> Optional[str]:
    if value is None or value == "":
        return None
    if not _HK1_RE.match(value):
        raise ValueError(
            "fingerprints must be 'hk1:<32 hex chars>' — raw values are "
            "never accepted at this boundary")
    return value


class DeviceRegisterRequest(BaseModel):
    """P0-04 request. Field-whitelist model: extra=forbidden (422)."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    device_uid: str
    hostname_fingerprint: str
    username_fingerprint: str
    network_fingerprint: Optional[str] = None
    os: str
    arch: str
    collector_version: str = ""

    @field_validator("device_uid")
    @classmethod
    def _uid(cls, v: str) -> str:
        return _validate_uid(v)

    @field_validator("hostname_fingerprint", "username_fingerprint",
                     "network_fingerprint")
    @classmethod
    def _hk1(cls, v: Optional[str]) -> Optional[str]:
        return _validate_hk1(v)

    @field_validator("os", "arch", "collector_version")
    @classmethod
    def _safe_len(cls, v: str) -> str:
        if len(v) > 64:
            raise ValueError("field too long (max 64)")
        return v


class DeviceResponse(BaseModel):
    """P0-04 response: NO fingerprints, NO raw evidence, NO tenant
    internals beyond the caller's own org id. assignment_status is DERIVED
    (no open device_assignment row == unassigned); lifecycle status is the
    devices.status column."""
    model_config = ConfigDict(extra="forbid")

    device_id: str
    device_uid: str
    status: str                  # lifecycle: active | disabled | retired
    assignment_status: str       # derived: unassigned | assigned
    first_seen_at: str           # server-side
    last_seen_at: str            # server-side


# ---------------------------------------------------------------------------
# P0-05 Member CRUD
# ---------------------------------------------------------------------------

class MemberCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    display_name: str
    email_optional: Optional[str] = None

    @field_validator("display_name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not (1 <= len(v) <= 128):
            raise ValueError("display_name must be 1..128 chars")
        return v

    @field_validator("email_optional")
    @classmethod
    def _email(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v):
            raise ValueError("email_optional must be a bare email address")
        return v


class MemberUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    display_name: Optional[str] = None
    email_optional: Optional[str] = None
    status: Optional[str] = None

    @field_validator("status")
    @classmethod
    def _status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("active", "disabled"):
            raise ValueError("status must be 'active' or 'disabled'")
        return v


class MemberResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    member_id: str
    organization_id: str
    display_name: str
    email_optional: Optional[str]
    status: str
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# P0-06 Manual assignment
# ---------------------------------------------------------------------------

class AssignmentCreateRequest(BaseModel):
    """Manual deterministic assignment: the caller names the member; the
    server enforces the timeline. No automatic inference exists anywhere."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    member_id: str
    valid_from: Optional[str] = None   # explicit backdating allowed; the
                                       # service validates overlap in a
                                       # single transaction
    reason: Optional[str] = None

    @field_validator("member_id")
    @classmethod
    def _member(cls, v: str) -> str:
        if not v.startswith("mem_"):
            raise ValueError("member_id must reference an existing member")
        return v

    @field_validator("reason")
    @classmethod
    def _reason(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) > 512:
            raise ValueError("reason too long (max 512)")
        return v


class AssignmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignment_id: str
    device_id: str
    member_id: str
    valid_from: str
    valid_to: Optional[str]
    reason: Optional[str]
    created_at: str


# ---------------------------------------------------------------------------
# P1A-07 Usage events (HTTP projection of the P1A-03 ingest domain)
# ---------------------------------------------------------------------------

class UsageEventResponse(BaseModel):
    """One usage event, projected for its OWN organization. No raw content
    exists anywhere in usage_events; money fields are server-owned and
    NULL until the (out-of-scope) pricing slice runs."""
    model_config = ConfigDict(extra="forbid")

    id: str
    organization_id: str
    device_id: str
    device_uid: str
    member_id: Optional[str]
    provider: str
    provider_account_ref: Optional[str]
    model: str
    session_ref: str
    source_event_id: str
    started_at: str
    ended_at: str
    received_at: str
    input_tokens: int
    cached_input_tokens: int
    cache_write_tokens: int
    output_tokens: int
    reasoning_tokens: int
    request_count: int
    pricing_version: Optional[str]
    api_equivalent_cost_usd: Optional[str]
    source_type: str
    collector_version: str
    created_at: str


class UsageBatchItemResult(BaseModel):
    """Per-item batch outcome: created | duplicate | rejected."""
    model_config = ConfigDict(extra="forbid")

    status: str
    event_id: Optional[str] = None
    detail: Optional[str] = None


class UsageBatchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results: list[UsageBatchItemResult]


class UsageEventBatchRequest(BaseModel):
    """Batch envelope, enforced at the HTTP edge BEFORE any write:
    extra top-level keys, non-claim items, or more than 500 events are a
    whole-request 422 with zero writes (spec section 6.2)."""
    model_config = ConfigDict(extra="forbid")

    events: list[UsageEventClaim]

    @model_validator(mode="after")
    def _cap_size(self) -> "UsageEventBatchRequest":
        if len(self.events) > 500:
            raise ValueError("batch exceeds 500 events")
        return self
