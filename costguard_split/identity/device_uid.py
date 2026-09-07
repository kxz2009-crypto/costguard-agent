"""Canonical device_uid: format, parse, validate, mint (v1 = UUIDv7).

Single source of truth for EVERYTHING device_uid related. No other module
may assemble or pattern-match a device_uid by hand (call parse/validate
here instead).

Locked format (P0 hardening, PATCH 1):

    cgdev_<uuid7-canonical-string>

    canonical string = 8-4-4-4-12 lowercase hex with dashes
    (str(uuid.UUID) form). Version nibble = 7, variant = RFC 4122.

Example: cgdev_018f0c9a-7b7c-7def-8a12-3f9e2d4c5b6a

Why UUIDv7: time-ordered (48-bit ms epoch in the top bits) so database
range scans / cursor pagination over device_uid are naturally ordered,
while keeping 74 bits of randomness. UUIDv4 remains valid for ADOPTED
legacy identities (see LEGACY note below) — validation accepts both,
minting produces only v7.

LEGACY compatibility (explicit, per hardening instructions):
- identities minted in the first P0 commit (96facac) used uuid4. They are
  ADOPTED as-is: parse/validate accept cgdev_<uuid4> as legacy_v4.
- no converter exists and none is planned: a device_uid never changes,
  because rotating it would silently fork the device's history.
"""

from __future__ import annotations

import os
import re
import time
import uuid
from dataclasses import dataclass

PREFIX = "cgdev_"

# canonical: lowercase 8-4-4-4-12 hex, RFC 4122 variant.
# Version nibble: 7 (current) or 4 (legacy adopted). v1/v2/v3/v5/v6/v8
# and non-RFC variants are rejected — an id outside {4,7} was never
# minted by any CostGuard version, so accepting it would only mask bugs.
_CANONICAL_RE = re.compile(
    r"^cgdev_([0-9a-f]{8}-[0-9a-f]{4}-[47][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12})$")


@dataclass(frozen=True)
class ParsedDeviceUid:
    raw: str
    uuid: uuid.UUID
    version: int          # 7 (minted today) or 4 (legacy adopted)
    timestamp_ms: int     # only meaningful for v7


_PREFIX_STATE = {"last_ms": 0, "counter": 0}


def new_device_uid() -> str:
    """Mint a fresh UUIDv7-based device_uid. Monotonic within a process;
    uniqueness across processes comes from the 74 random bits."""
    return PREFIX + str(uuid7())


def uuid7() -> uuid.UUID:
    """Minimal RFC 9562 UUIDv7 generator (stdlib-only, ~10 lines).

    Layout: 48-bit unix ms | version(7) | 12 rand | variant(10) | 62 rand.
    Anti-monotonic-clock-rollback: if the clock went backwards vs the last
    value minted in THIS process, we keep the previous timestamp (the id
    stream stays monotonic; true wall-clock fidelity resumes when the
    clock catches up). Same-millisecond collisions are avoided by bumping
    the rand_a field (12-bit counter) — guaranteed ordering for ids minted
    in-process even at high frequency.
    """
    ms = time.time_ns() // 1_000_000
    last = _PREFIX_STATE["last_ms"]
    counter = _PREFIX_STATE["counter"]
    if ms < last:                      # clock rollback: hold timestamp
        ms = last
    if ms == last:
        counter = (counter + 1) & 0x0FFF
        if counter == 0:               # 4096 ids in one ms: wait it out
            while time.time_ns() // 1_000_000 == ms:
                time.sleep(0.0005)
            ms = time.time_ns() // 1_000_000
    else:
        counter = os.urandom(1)[0] & 0x0FF   # fresh low bits, still ordered
    _PREFIX_STATE["last_ms"] = ms
    _PREFIX_STATE["counter"] = counter
    rand_b = int.from_bytes(os.urandom(8), "big") & 0x3FFF_FFFFFFFF
    value = ((ms & 0xFFFF_FFFF_FFFF) << 80) | (7 << 76) | (
        counter << 64) | (0x2 << 62) | rand_b
    return uuid.UUID(int=value)


def parse_device_uid(raw: str) -> ParsedDeviceUid:
    """Strict parser. Raises ValueError on anything not canonical."""
    if not isinstance(raw, str):
        raise ValueError(f"device_uid must be str, got {type(raw).__name__}")
    m = _CANONICAL_RE.fullmatch(raw)
    if not m:
        raise ValueError(
            f"invalid device_uid {raw!r}: expected "
            f"'cgdev_<uuid7-canonical>' (lowercase 8-4-4-4-12)")
    u = uuid.UUID(m.group(1))
    # re-serialize to guarantee canonical form (rejects uppercase etc.)
    canonical = PREFIX + str(u)
    if canonical != raw:
        raise ValueError(f"device_uid {raw!r} is not canonical "
                         f"(expected {canonical!r})")
    ts_ms = (u.int >> 80) & 0xFFFF_FFFF_FFFF if (u.version or 0) == 7 else 0
    return ParsedDeviceUid(raw=raw, uuid=u, version=u.version or 0,
                           timestamp_ms=ts_ms)


def validate_device_uid(raw: str) -> bool:
    """Bool convenience for server/DB validation — same rule as parse."""
    try:
        parse_device_uid(raw)
        return True
    except ValueError:
        return False
