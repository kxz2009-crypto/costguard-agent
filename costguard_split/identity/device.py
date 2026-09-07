"""Persistent device identity for CostGuard Split (P0-03, hardened).

PATCH 2 (COSTGUARD_HOME): every path goes through paths.resolve_home()
(call-time; explicit arg > env > legacy default). No import-time caching.

PATCH 3 (adopt-before-mint): get_or_create_identity()
    1. read existing device.json
    2. STRICT validate (parse_device_uid canonical rule)
    3. valid   -> ADOPT (return as-is; first_seen_at preserved)
    4. absent  -> mint (atomic write)
    5. corrupt -> raise DeviceIdentityCorrupted. NEVER silently re-mint:
       a rotated uid silently forks the device's history and would poison
       member attribution / billing. Recovery is explicit (see below).

Recovery path when corrupted:
    quarantine_corrupted_identity() moves the broken file aside
    (device.json.corrupt-<ts>, still 0600) and the NEXT call mints fresh.
    Operator-visible action, never automatic.

Durability: tmp file in the same dir + fsync + os.replace (atomic on
POSIX & Windows) + 0600. Concurrent first initialization: os.replace is
atomic, and adopt-or-keep semantics (see get_or_create_identity) ensure
exactly ONE identity wins; losers ADOPT the winner instead of overwriting.

LOCAL ONLY (explicit per review): hostname/username live here for operator
display. They must NEVER appear in a sync DTO — the data layer receives
only fingerprints (identity/device.py hashed_evidence). P0-04 API schema
must whitelist fields, not serialize this file.
"""

from __future__ import annotations

import json
import os
import platform
import threading
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .. import paths
from . import device_uid as duid
from . import fingerprints as fp

DEVICE_JSON_NAME = "device.json"

# Identity confidence weights (spec §11) — helper for P0-08. The score
# NEVER triggers automatic member attribution.
CONFIDENCE_WEIGHTS = {
    "persistent_device_uid": 60,
    "known_hostname": 15,
    "known_username": 10,
    "known_os": 5,
    "known_network": 5,
    "continuous_timestamps": 5,
}


class DeviceIdentityCorrupted(RuntimeError):
    """device.json exists but is not a valid identity.

    The file is NOT overwritten automatically. Recovery:
        quarantine_corrupted_identity()  then re-run get_or_create_identity
    """

    def __init__(self, path: Path, reason: str):
        self.path = path
        self.reason = reason
        super().__init__(
            f"device identity at {path} is corrupted ({reason}). "
            f"Recover explicitly with "
            f"quarantine_corrupted_identity({path!r}) — this preserves the "
            f"broken file for inspection — then re-run identity creation.")


@dataclass
class DeviceIdentity:
    """Local identity record. `hostname`/`username` are LOCAL ONLY display
    evidence; the Split data layer receives only fingerprints."""
    device_uid: str
    device_name: str
    first_seen_at: str
    hostname: str = ""
    username: str = ""
    os_name: str = ""
    arch: str = ""
    collector_version: str = ""
    schema: int = 2

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "DeviceIdentity":
        d = json.loads(text)
        if not isinstance(d, dict):
            raise ValueError("identity JSON must be an object")
        for key in ("device_uid", "device_name", "first_seen_at"):
            if not isinstance(d.get(key), str) or not d.get(key):
                raise ValueError(f"identity field {key!r} missing/empty")
        duid.parse_device_uid(d["device_uid"])  # strict canonical check
        return cls(
            device_uid=d["device_uid"],
            device_name=d["device_name"],
            first_seen_at=d["first_seen_at"],
            hostname=d.get("hostname", ""),
            username=d.get("username", ""),
            os_name=d.get("os_name", ""),
            arch=d.get("arch", ""),
            collector_version=d.get("collector_version", ""),
            schema=int(d.get("schema", 1)),
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _collect_evidence() -> dict:
    """Best-effort local evidence. No network calls, ever."""
    try:
        hostname = platform.node() or ""
    except Exception:
        hostname = ""
    try:
        username = os.getlogin()
    except Exception:  # non-tty (cron, CI)
        import getpass
        try:
            username = getpass.getuser()
        except Exception:
            username = ""
    try:
        os_name = platform.system() or "unknown"
        arch = platform.machine() or "unknown"
    except Exception:
        os_name = arch = "unknown"
    return {"hostname": hostname, "username": username,
            "os": os_name, "arch": arch}


def _write_identity_atomic(path: Path, ident: DeviceIdentity) -> None:
    """tmp -> fsync -> os.replace -> chmod 0600. Atomic on POSIX+Windows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    import uuid as _uuid
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}.{_uuid.uuid4().hex[:8]}")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(ident.to_json() + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)               # atomic: winner takes all
    finally:
        tmp.unlink(missing_ok=True)


def load_identity(home: Path | str | None = None) -> Optional[DeviceIdentity]:
    """Read + strict-validate. Returns None if absent.

    Raises DeviceIdentityCorrupted on corrupt/partial/foreign content —
    callers must NOT catch-and-mint (that is the silent-rotation bug this
    patch exists to kill).
    """
    f = paths.device_json_path(home)
    if not f.exists():
        return None
    try:
        text = f.read_text(encoding="utf-8")
        return DeviceIdentity.from_json(text)
    except (json.JSONDecodeError, ValueError, TypeError, KeyError,
            UnicodeDecodeError) as exc:
        raise DeviceIdentityCorrupted(f, str(exc)) from exc


def quarantine_corrupted_identity(path: Path | str | None = None) -> Path:
    """Move a corrupted device.json aside (explicit operator action).

    Returns the quarantine path. The next get_or_create_identity() will
    then mint a fresh identity — visible, deliberate, auditable.
    """
    f = paths.device_json_path(path)
    if not f.exists():
        raise FileNotFoundError(f)
    ts = _now_iso().replace(":", "").replace("+", "_")
    dst = f.with_name(f"{f.name}.corrupt-{ts}")
    os.replace(f, dst)
    os.chmod(dst, 0o600)
    return dst


_INIT_LOCK = threading.Lock()   # same-process serialization; cross-process
                                # safety comes from atomic os.replace


def get_or_create_identity(home: Path | str | None = None,
                           collector_version: str = "") -> DeviceIdentity:
    """Adopt existing identity or mint exactly one new one.

    Concurrency: two processes may both find nothing and mint; the SECOND
    os.replace wins on disk, but both processes re-READ after replace and
    return the on-disk winner (adopt-before-return), so exactly one
    identity survives and every caller agrees on it.
    """
    f = paths.device_json_path(home)
    with _INIT_LOCK:
        return _get_or_create_locked(f, home, collector_version)


def _get_or_create_locked(f: Path, home, collector_version: str
                          ) -> DeviceIdentity:
    existing = load_identity(home)
    if existing is not None:
        return existing                     # ADOPT (uid never rotates)
    ev = _collect_evidence()
    fresh = DeviceIdentity(
        device_uid=duid.new_device_uid(),
        device_name=ev["hostname"] or "unknown-device",
        first_seen_at=_now_iso(),
        hostname=ev["hostname"],
        username=ev["username"],
        os_name=ev["os"],
        arch=ev["arch"],
        collector_version=collector_version,
    )
    _write_identity_atomic(f, fresh)
    # adopt the on-disk winner (matters under concurrent first init)
    winner = load_identity(home)
    if winner is not None:
        return winner
    return fresh


def load_or_create_key(home: Path | str | None = None) -> bytes:
    """Deployment-local fingerprint key (0600) for HMAC fingerprints."""
    return fp._load_or_create_key(paths.fingerprint_key_path(home))


def hashed_evidence(identity: DeviceIdentity,
                    key: bytes) -> dict:
    """The ONLY shape of evidence that may enter the Split data layer or a
    sync DTO. Raw hostname/username/IP can never pass through here."""
    return {
        "device_uid": identity.device_uid,
        "hostname_hash": fp.hostname_fingerprint(identity.hostname, key)
        if identity.hostname else "",
        "username_hash": fp.username_fingerprint(identity.username, key)
        if identity.username else "",
        "os": identity.os_name,
        "arch": identity.arch,
        "collector_version": identity.collector_version,
        "first_seen_at": identity.first_seen_at,
    }


def confidence_score(*, device_uid_valid: bool,
                     hostname_known: bool = False,
                     username_known: bool = False,
                     os_known: bool = False,
                     network_known: bool = False,
                     timestamps_continuous: bool = False) -> int:
    """Deterministic scoring (spec §11). An aid for P0-08 — never an
    attribution trigger."""
    score = 0
    if device_uid_valid:
        score += CONFIDENCE_WEIGHTS["persistent_device_uid"]
    if hostname_known:
        score += CONFIDENCE_WEIGHTS["known_hostname"]
    if username_known:
        score += CONFIDENCE_WEIGHTS["known_username"]
    if os_known:
        score += CONFIDENCE_WEIGHTS["known_os"]
    if network_known:
        score += CONFIDENCE_WEIGHTS["known_network"]
    if timestamps_continuous:
        score += CONFIDENCE_WEIGHTS["continuous_timestamps"]
    return min(score, 100)
