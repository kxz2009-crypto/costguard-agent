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
import time
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
    """tmp(0600 via O_EXCL) -> fsync -> os.replace -> stat verify.

    B-1a: the file's 0600 mode is set at creation time with an explicit
    os.open(..., 0o600) — never delegated to umask — and re-verified on the
    final path after replace. Atomic on POSIX & Windows.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    import uuid as _uuid
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}.{_uuid.uuid4().hex[:8]}")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.fchmod(fd, 0o600)            # belt & braces vs odd umasks
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(ident.to_json() + "\n")
                fh.flush()
                os.fsync(fh.fileno())
        except Exception:
            os.close(fd)                    # fdopen consumed it only on success
            raise
        os.replace(tmp, path)               # atomic: winner takes all
    finally:
        tmp.unlink(missing_ok=True)
    # post-replace verification: final artifact must really be 0600
    if (os.stat(path).st_mode & 0o777) != 0o600:
        os.chmod(path, 0o600)


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


class DeviceIdentityInitializationTimeout(RuntimeError):
    """A follower waited for the writer's device.json and timed out.

    Raised INSTEAD of minting a second identity — a fallback mint here is
    exactly the multiprocess ghost-UID bug this module exists to prevent.
    Recovery: retry (the writer usually finished by now) or inspect the
    home directory for a stale device.json.lock.
    """

    def __init__(self, path: Path, waited_s: float):
        self.path = path
        self.waited_s = waited_s
        super().__init__(
            f"timed out after {waited_s:.1f}s waiting for {path} to appear "
            f"(another process holds the initialization lock). NOT minting a "
            f"second identity — retry once the writer finishes or remove the "
            f"stale {path}.lock if its owner is confirmed dead.")


# --- cross-process single-writer initialization (B-1) -----------------------
#
# threading.Lock alone cannot guard across processes. The correctness
# primitive is a lock FILE claimed with O_CREAT|O_EXCL (atomic exclusive
# creation on POSIX and Windows):
#
#   writer   : claims <name>.lock -> re-checks device.json -> absent: mint
#              once, atomic-write, re-read canonical, return canonical UID
#   follower : claim fails (EEXIST) -> NEVER mints -> polls for device.json
#              to appear (bounded) -> adopts and returns it
#   stale    : lock files carry {"pid", "created_at"}; a lock whose pid is
#              dead AND age > STALE_LOCK_SEC is reclaimed by breaking it
#              (crash-before-write cannot be signalled any other way)
#
# A lock file may reference a recycled pid; the age threshold bounds that
# risk (a writer holds the lock for milliseconds). The in-process
# threading.Lock stays as an optimization so N threads don't stampede the
# filesystem; it provides NO correctness guarantee by itself.

LOCK_NAME = "device.json.lock"
LOCK_TIMEOUT_S = 10.0            # follower bounded wait (spec: 5-10s)
FOLLOWER_POLL_S = 0.02
STALE_LOCK_SEC = 30.0            # dead-pid lock younger than this: keep waiting


class _InitLock:
    """Context manager: cross-process single-writer claim on identity mint."""

    def __init__(self, target: Path):
        self.lock_path = target.with_name(target.name + ".lock")
        self.is_writer = False

    def _read_owner(self) -> dict:
        try:
            return json.loads(self.lock_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _owner_dead(self, owner: dict) -> bool:
        pid = owner.get("pid")
        if not isinstance(pid, int) or pid <= 0:
            return False                     # UNPARSABLE: never assume dead.
            # A follower can read the lock BETWEEN O_EXCL creation and the
            # owner's payload write; treating that as "dead" would break a
            # LIVE writer's lock and mint a second identity (observed race).
            # Unparsable locks age out via mtime instead (see _try_break_stale).
        try:
            os.kill(pid, 0)                  # exists? (no-op signal)
            return False
        except ProcessLookupError:
            return True
        except PermissionError:
            return False                     # exists, owned by someone else
        except OSError:
            return False                     # conservative: treat as alive

    def _try_break_stale(self) -> bool:
        """Reclaim a provably abandoned lock. Returns True if lock is gone.

        Policy: a lock is stale only when BOTH
          - its owner payload is parsable AND the pid is provably dead, AND
          - the lock file is older than STALE_LOCK_SEC (mtime truth).
        Anything ambiguous (payload not yet written, unknown pid state,
        unparsable age) -> keep waiting; a live writer holds the lock for
        milliseconds, so STALE_LOCK_SEC is a safe ceiling for honest owners.
        """
        owner = self._read_owner()
        try:
            # st_mtime is epoch-based -> compare against time.time(), NOT
            # time.monotonic() (monotonic is uptime-relative on Linux).
            age = max(0.0, time.time() - self.lock_path.stat().st_mtime)
        except OSError:
            return True                      # lock vanished: race again
        if age <= STALE_LOCK_SEC:
            return False                     # too fresh to judge
        if owner and not self._owner_dead(owner):
            return False                     # known live owner
        if not owner:
            return False                     # ambiguous payload: never break
        try:
            self.lock_path.unlink(missing_ok=True)
        except OSError:
            return False
        return True

    def __enter__(self) -> "_InitLock":
        fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                     0o600)
        try:
            payload = json.dumps({
                "pid": os.getpid(),
                "created_at": _now_iso(),
                "created_mono": _monotonic(),
            }).encode("utf-8")
            os.write(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)
        self.is_writer = True
        return self

    def __exit__(self, *exc) -> None:
        if self.is_writer:
            try:
                self.lock_path.unlink(missing_ok=True)
            except OSError:
                pass
            self.is_writer = False


def _monotonic() -> float:
    import time
    return time.monotonic()


def _acquire_init_lock(target: Path) -> _InitLock:
    """Become the writer, or wait as a follower until device.json exists.

    Returns an acquired _InitLock (writer role) — caller MUST mint + write.
    Raises DeviceIdentityInitializationTimeout if follower wait expires.
    """
    target.parent.mkdir(parents=True, exist_ok=True)   # lock needs a real dir
    deadline = _monotonic() + LOCK_TIMEOUT_S
    while True:
        try:
            return _InitLock(target).__enter__()
        except FileExistsError:
            lock = _InitLock(target)
            if lock._try_break_stale():
                continue                     # reclaimed: race again
            # follower: wait for the winner's file, bounded
            if target.exists():
                winner = load_identity(target.parent)
                if winner is not None:
                    raise _FollowerAdopted(winner)
            if _monotonic() >= deadline:
                raise DeviceIdentityInitializationTimeout(
                    target, LOCK_TIMEOUT_S)
            import time
            time.sleep(FOLLOWER_POLL_S)


class _FollowerAdopted(Exception):
    """Internal control flow: follower found the winner's identity."""

    def __init__(self, identity: DeviceIdentity):
        self.identity = identity


_INIT_LOCK = threading.Lock()   # in-process optimization ONLY; cross-process
                                # correctness comes from _InitLock (lock file)


def get_or_create_identity(home: Path | str | None = None,
                           collector_version: str = "") -> DeviceIdentity:
    """Adopt existing identity or mint exactly ONE under a cross-process
    single-writer lock (B-1).

    Invariants (hold for N concurrent processes on an empty home):
    - Only the lock holder may mint or replace device.json.
    - Losers NEVER mint and NEVER return their own candidate — they wait
      (bounded) and adopt the canonical on-disk identity.
    - Every successful call returns the device_uid that is on disk.
    - device.json ends up 0600 (creation-time mode, umask-independent).
    - Lock file is removed on all exits; stale dead-owner locks are
      reclaimed after STALE_LOCK_SEC (never waited on forever).
    """
    f = paths.device_json_path(home)
    with _INIT_LOCK:                        # same-process efficiency only
        # Fast path: valid identity already on disk -> ADOPT (no lock file
        # churn). Re-harden permissive modes in place (B-1a), same UID.
        existing = load_identity(home)
        if existing is not None:
            _harden_mode(f)
            return existing
        try:
            lock = _acquire_init_lock(f)
        except _FollowerAdopted as adopted:
            return adopted.identity         # winner finished: adopt, done
        # WRITER ROLE (we own the lock file now)
        try:
            return _mint_under_lock(f, home, collector_version)
        finally:
            lock.__exit__(None, None, None)


def _mint_under_lock(f: Path, home, collector_version: str) -> DeviceIdentity:
    """Writer flow: re-check (another writer may have finished while we
    raced for the lock) -> mint exactly once -> atomic write -> re-read the
    canonical file and return IT (never the in-memory candidate)."""
    existing = load_identity(home)
    if existing is not None:                # double-check under lock
        _harden_mode(f)
        return existing
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
    winner = load_identity(home)            # canonical = what's on disk
    if winner is None:                      # fs-level anomaly: fail loudly
        raise DeviceIdentityCorrupted(f, "identity vanished after write")
    return winner


def _harden_mode(f: Path) -> None:
    """B-1a policy: valid identity with over-permissive mode is chmod'd to
    0600 in place — same UID, no rotation, silent security fix."""
    try:
        if (os.stat(f).st_mode & 0o777) != 0o600:
            os.chmod(f, 0o600)
    except OSError:
        pass


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
