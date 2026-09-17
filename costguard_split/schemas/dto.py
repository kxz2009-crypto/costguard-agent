"""Split trust-boundary DTOs (PATCH 10) + safe evidence DTO (review note).

P0→P1 boundary contract (code is the contract; P1 ingestion will import
these — nothing here performs I/O):

  Collector MAY CLAIM          Server MUST DETERMINE
  -------------------          ---------------------
  provider                     organization_id
  source_event_id              member attribution (event-time)
  session reference            pricing_version
  model                        api_equivalent_cost_usd (Decimal)
  started_at / ended_at        attribution_confidence
  token counters (ints)        canonical received_at
  request_count                duplicate decision (idempotency)
  device_uid

  Server MUST NOT TRUST client-supplied: organization_id, member_id,
  api_equivalent_cost, pricing data, attribution_confidence.

Event idempotency (P1, decided now): the legacy Agent key
(source, session_ref, timestamp) is NOT acceptable — several legal
events can share one session and one second. The Split ingest key will
be (organization_id, device_uid, provider, source_event_id) with
source_event_id defined by the collector as provider-native-unique or
collector-derived-unique; helper below normalizes it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# P1A-02 canonical Pydantic boundary. Re-exported here so P0 import paths
# remain valid while all new code imports costguard_split.schemas.usage.
from .usage import UsageEventClaim

# ---------------------------------------------------------------------------
# Safe evidence DTO (LOCAL-ONLY raw values never leave the device):
# sync/registration payloads contain fingerprints ONLY. P0-04 must
# whitelist these fields — never serialize device.json directly.
# ---------------------------------------------------------------------------

EVIDENCE_DTO_FIELDS = (
    "device_uid",          # cgdev_* (identity, not a secret)
    "hostname_fingerprint",  # hk1:<digest>
    "username_fingerprint",  # hk1:<digest>
    "network_fingerprint",   # hk1:<digest> or None (P0-07)
    "os", "arch",
    "first_seen_at", "last_seen_at",
    "collector_version",
)

_FORBIDDEN_DTO_KEYS = ("hostname", "username", "raw_ip", "ip",
                       "prompt", "response", "content")


@dataclass
class DeviceEvidenceDTO:
    """The only sanctioned wire shape for device evidence."""
    device_uid: str
    hostname_fingerprint: str
    username_fingerprint: str
    os: str
    arch: str
    first_seen_at: str
    last_seen_at: str
    collector_version: str
    network_fingerprint: Optional[str] = None

    def validate(self) -> list[str]:
        errors = []
        from ..identity.device_uid import validate_device_uid
        if not validate_device_uid(self.device_uid):
            errors.append("device_uid malformed")
        from ..identity import fingerprints as fp
        for name in ("hostname_fingerprint", "username_fingerprint"):
            value = getattr(self, name)
            try:
                fp.parse_fingerprint(value)
            except ValueError as exc:
                errors.append(f"{name}: {exc}")
        if self.network_fingerprint is not None:
            try:
                fp.parse_fingerprint(self.network_fingerprint)
            except ValueError as exc:
                errors.append(f"network_fingerprint: {exc}")
        return errors


def assert_dto_never_carries_raw(payload: dict) -> None:
    """Hard gate: raise if a DTO/payload contains any forbidden raw key."""
    bad = sorted(set(payload) & set(_FORBIDDEN_DTO_KEYS))
    if bad:
        raise ValueError(f"payload carries forbidden raw keys: {bad}")


# ---------------------------------------------------------------------------
# P1 usage-event claim helpers. UsageEventClaim is imported above from the
# canonical Pydantic boundary module; this file retains the legacy import path.
# ---------------------------------------------------------------------------


def canonical_source_event_id(provider: str, native_id: str) -> str:
    """P1 idempotency helper: normalize a provider-native event id into a
    stable unique string. Replaces the legacy
    (source, session_ref, timestamp) key, which collides when one session
    emits several events in the same second."""
    provider = provider.strip().lower()
    native = native_id.strip()
    if not provider or not native:
        raise ValueError("provider and native id are required")
    if not re.fullmatch(r"[a-z0-9_-]{1,32}", provider):
        raise ValueError(f"unusable provider name: {provider!r}")
    return f"{provider}:{native}"
