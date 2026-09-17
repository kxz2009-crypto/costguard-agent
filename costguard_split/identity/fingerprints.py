"""Keyed fingerprints — proof-of-sameness without storing the raw value.

Rules (spec §6.3, hardening PATCH 7):
- hostname / username / normalized IP are NEVER stored raw.
- Stored format: "hk1:<digest>" where digest = HMAC-SHA256(key, value)
  truncated to 32 hex chars. The hk1 prefix = hash-key VERSION 1, so a
  future key rotation can tell which historical key a fingerprint used.
  The key itself is NEVER stored in the database.
- Raw IP != identity: network_hash = hk1:HMAC(key, normalized_ip).
  Interface provided now (P0-03/07); server-side secret handling is
  P0-07. The interface takes the key explicitly so the caller decides
  which key (local file vs server secret) applies.
- The local key file lives in the CostGuard home (0600), resolved via
  paths.py — no hardcoded paths, no import-time caching.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
from pathlib import Path

HASH_VERSION = "hk1"
_DIGEST_LEN = 32


def fingerprint(value: str, key: bytes) -> str:
    """hk1:HMAC-SHA256(key, value)[0:32]. Stable, non-reversible, versioned."""
    if not isinstance(value, str) or value == "":
        raise ValueError("fingerprint value must be a non-empty string")
    if not isinstance(key, bytes) or len(key) < 32:
        raise ValueError("fingerprint key must be >=32 random bytes")
    digest = hmac.new(key, value.encode("utf-8"),
                      hashlib.sha256).hexdigest()[:_DIGEST_LEN]
    return f"{HASH_VERSION}:{digest}"


def parse_fingerprint(stored: str) -> tuple[str, str]:
    """Split 'hk1:<digest>' -> (version, digest). Raises on foreign format."""
    version, sep, digest = stored.partition(":")
    if not sep or version != HASH_VERSION or not re.fullmatch(
            r"[0-9a-f]{32}", digest):
        raise ValueError(f"malformed fingerprint: {stored!r}")
    return version, digest


def hostname_fingerprint(hostname: str, key: bytes) -> str:
    """Case-normalized hostname fingerprint (DNS names are case-insensitive)."""
    return fingerprint(hostname.strip().lower(), key)


def username_fingerprint(username: str, key: bytes) -> str:
    """Username fingerprint. NOT a user identity — equality evidence only."""
    return fingerprint(username.strip(), key)


def normalize_ip(ip: str) -> str:
    """Canonicalize an IP for hashing (IPv4 as-is; IPv6 compressed/lower).

    Garbage input raises ValueError — never hash something we cannot
    normalize deterministically.
    """
    import ipaddress
    return str(ipaddress.ip_address(ip.strip()))


def network_fingerprint(ip: str, key: bytes) -> str:
    """hk1:HMAC(key, normalized_ip). Raw IP never stored or logged."""
    return fingerprint(normalize_ip(ip), key)


def new_fingerprint_key() -> bytes:
    return os.urandom(32)


def _load_or_create_key(key_path: Path) -> bytes:
    """Deployment-local HMAC key (0600), created once.

    P1-NON-BLOCKING hardening (recorded, not expanded):
    - created via O_CREAT|O_EXCL 0600 + atomic replace (umask-independent,
      mirrors device.json discipline)
    - an existing MALFORMED key file is NOT silently rotated: rotation
      invalidates every fingerprint ever computed with the old key, which
      silently re-identifies members. The caller gets a loud error and an
      explicit recovery action instead (quarantine + replace by operator).
      Full key-rotation protocol stays P1 (VPS review: NON-BLOCKING).
    """
    key_path = Path(key_path)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    if key_path.exists():
        raw = key_path.read_text(encoding="utf-8").strip()
        if re.fullmatch(r"[0-9a-f]{64}", raw):
            key = bytes.fromhex(raw)
        else:
            raise ValueError(
                f"fingerprint key at {key_path} is malformed — refusing to "
                f"rotate it automatically (rotation would silently re-"
                f"identify all members ever fingerprinted with the old "
                f"key). Recover explicitly: inspect the file, then quarantine"
                f" (rename) or replace it by hand, and re-run.")
        if (key_path.stat().st_mode & 0o777) != 0o600:
            os.chmod(key_path, 0o600)
        return key
    key = os.urandom(32)
    import uuid as _uuid
    tmp = key_path.with_name(
        f"{key_path.name}.tmp.{os.getpid()}.{_uuid.uuid4().hex[:8]}")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(key.hex() + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, key_path)
    finally:
        tmp.unlink(missing_ok=True)
    os.chmod(key_path, 0o600)
    return key


def key_file_for(home: Path | str | None = None) -> Path:
    from .. import paths
    return paths.fingerprint_key_path(home)


__all__ = [
    "fingerprint", "parse_fingerprint", "hostname_fingerprint",
    "username_fingerprint", "network_fingerprint", "normalize_ip",
    "new_fingerprint_key", "_load_or_create_key", "key_file_for",
    "HASH_VERSION",
]
