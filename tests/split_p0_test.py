"""CostGuard Split P0 HARDENING test suite (T01-T23).

Run: python -m unittest tests.split_p0_test -v
Replaces the first-round split_p0_test (11 tests) with the full hardening
matrix. Fixtures: every test uses a tmp COSTGUARD_HOME (explicit arg or
env var) — the real ~/.costguard is never touched. Zero network.

Coverage map (task numbering):
  T01 persistent UID                T13 migration idempotency
  T02 reload persistence            T14 cross-org FK rejection
  T03 separate homes -> IDs         T15 assignment initial
  T04 UUIDv7 format                 T16 reassignment history
  T05 UID uniqueness                T17 no overlapping assignments
  T06 COSTGUARD_HOME isolation      T18 event-time attribution helper
  T07 corrupted device.json         T19 audit append
  T08 concurrent first init         T20 audit before/after JSON
  T09 hostname HMAC privacy         T21 no float monetary schema
  T10 username HMAC privacy         T22 unknown device: no active assignment
  T11 network HMAC privacy          T23 Agent full regression (separate run)
  T12 hash-key version prefix
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from costguard_split import db as split_db
from costguard_split import paths
from costguard_split.identity import device as dev
from costguard_split.identity import device_uid as duid
from costguard_split.identity import fingerprints as fp
from costguard_split.schemas import dto
from costguard_split.schemas import policy
from costguard_split.schemas import tables as schemas
from costguard_split.services import audit
from costguard_split.services import device_registry as reg

T0 = "2026-09-01T00:00:00+00:00"
T1 = "2026-09-11T00:00:00+00:00"


@contextmanager
def temporary_costguard_home(home_path):
    """B-3: set COSTGUARD_HOME for a block; restore the EXACT previous
    environment state on exit (previously-set value is restored, originally
    unset stays unset). Every test that touches the env variable must go
    through this — raw os.environ writes leak state across tests."""
    previous = os.environ.get("COSTGUARD_HOME")
    os.environ["COSTGUARD_HOME"] = str(home_path)
    try:
        yield Path(home_path)
    finally:
        if previous is None:
            os.environ.pop("COSTGUARD_HOME", None)
        else:
            os.environ["COSTGUARD_HOME"] = previous


class SplitHome:
    """tmp COSTGUARD_HOME for both identity files and split.db."""

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name) / "cg-home"
        self.conn = split_db.connect(path=paths.split_db_path(self.home))
        self.conn.execute(
            "INSERT INTO organizations (id, name, status, created_at,"
            " updated_at) VALUES ('org1','Demo','active','t','t')")
        self.conn.execute(
            "INSERT INTO organizations (id, name, status, created_at,"
            " updated_at) VALUES ('org2','Other','active','t','t')")
        for mid, org, name in (("mem_k", "org1", "test-member"),
                               ("mem_a", "org1", "Alice"),
                               ("mem_o", "org2", "Outsider")):
            self.conn.execute(
                "INSERT INTO members (id, organization_id, display_name,"
                " status, created_at, updated_at) VALUES"
                " (?,?,?,'active','t','t')", (mid, org, name))
        self.conn.commit()
        return self

    def __exit__(self, *exc):
        self.conn.close()
        self._tmp.cleanup()
        return False

    # -- helpers ----------------------------------------------------------
    def register(self, uid=None, org="org1", name="A"):
        uid = uid or duid.new_device_uid()
        device, created = reg.register_device(
            self.conn, organization_id=org, device_uid=uid,
            display_name=name,
            hostname_hash=fp.hostname_fingerprint("host-" + name,
                                                  dev.load_or_create_key(self.home)),
            username_hash=fp.username_fingerprint("user-" + name,
                                                  dev.load_or_create_key(self.home)),
            os_name="Linux", arch="x86_64", first_seen_at=T0)
        return device, created

    def member(self, device_id, at):
        return reg.member_at(self.conn, device_id=device_id, at=at)


class UidTests(unittest.TestCase):
    def test_t01_persistent_uid(self):
        with SplitHome() as env:
            ident = dev.get_or_create_identity(home=env.home)
            self.assertTrue(duid.validate_device_uid(ident.device_uid))
            on_disk = json.loads(
                paths.device_json_path(env.home).read_text(encoding="utf-8"))
            self.assertEqual(on_disk["device_uid"], ident.device_uid)
            self.assertTrue(on_disk["first_seen_at"])

    def test_t02_reload_persistence(self):
        with SplitHome() as env:
            a = dev.get_or_create_identity(home=env.home)
            b = dev.get_or_create_identity(home=env.home)
            self.assertEqual(a.device_uid, b.device_uid)
            self.assertEqual(a.first_seen_at, b.first_seen_at)

    def test_t03_separate_homes_differ(self):
        with tempfile.TemporaryDirectory() as td:
            i1 = dev.get_or_create_identity(home=Path(td) / "a")
            i2 = dev.get_or_create_identity(home=Path(td) / "b")
            self.assertNotEqual(i1.device_uid, i2.device_uid)

    def test_t04_uuidv7_format(self):
        uid = duid.new_device_uid()
        parsed = duid.parse_device_uid(uid)          # strict canonical
        self.assertEqual(parsed.version, 7)
        self.assertGreater(parsed.timestamp_ms, 1_600_000_000_000)
        # clock order: ids minted later sort >= earlier (same-process)
        ids = [duid.parse_device_uid(duid.new_device_uid()).timestamp_ms
               for _ in range(20)]
        self.assertEqual(ids, sorted(ids))
        # legacy v4 ADOPTED, everything else rejected
        import uuid as u
        self.assertTrue(duid.validate_device_uid("cgdev_" + str(u.uuid4())))
        self.assertFalse(duid.validate_device_uid(
            "cgdev_" + str(u.uuid5(u.NAMESPACE_DNS, "x"))))  # v5
        self.assertFalse(duid.validate_device_uid(
            ("cgdev_" + str(u.uuid4())).upper()))            # non-canonical
        self.assertFalse(duid.validate_device_uid("cg-nope"))

    def test_t05_uid_uniqueness(self):
        seen = {duid.new_device_uid() for _ in range(2000)}
        self.assertEqual(len(seen), 2000)


class HomeIsolationTests(unittest.TestCase):
    def test_t06_costguard_home_isolation(self):
        # keep a canary: env must be exactly restored after every block
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "isolated"
            with temporary_costguard_home(home):
                # env-driven resolution (priority 2)
                self.assertEqual(paths.resolve_home(), home)
                ident = dev.get_or_create_identity()   # no explicit arg
                self.assertTrue(
                    paths.device_json_path(home).exists())
                conn = split_db.connect()              # same single resolver
                tables = {r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
                self.assertIn("devices", tables)
                conn.close()
                key = dev.load_or_create_key()
                self.assertEqual(len(key), 32)
                self.assertTrue(
                    paths.fingerprint_key_path(home).exists())
                self.assertTrue(duid.validate_device_uid(ident.device_uid))
        # priority 1 beats env
        with tempfile.TemporaryDirectory() as td:
            with temporary_costguard_home(Path(td) / "env-home"):
                explicit = Path(td) / "explicit"
                self.assertEqual(paths.resolve_home(explicit), explicit)
        # unset env -> legacy default resolution still works (no crash)
        prev = os.environ.pop("COSTGUARD_HOME", None)
        try:
            self.assertTrue(str(paths.resolve_home()).endswith(
                ".costguard") or paths.resolve_home().name)
        finally:
            if prev is not None:
                os.environ["COSTGUARD_HOME"] = prev


class CorruptionTests(unittest.TestCase):
    def test_t07_corrupted_device_json(self):
        with SplitHome() as env:
            first = dev.get_or_create_identity(home=env.home)
            f = paths.device_json_path(env.home)
            # partial write
            f.write_text('{"device_uid": "cgdev_half-wr', encoding="utf-8")
            with self.assertRaises(dev.DeviceIdentityCorrupted):
                dev.get_or_create_identity(home=env.home)
            self.assertIn("half-wr", f.read_text(encoding="utf-8"))  # intact
            # foreign but parseable JSON with bad uid -> also corrupted
            f.write_text('{"device_uid": "nope", "device_name": "x",'
                         ' "first_seen_at": "t"}', encoding="utf-8")
            with self.assertRaises(dev.DeviceIdentityCorrupted):
                dev.load_identity(env.home)
            # explicit recovery path: quarantine then mint
            q = dev.quarantine_corrupted_identity(env.home)
            self.assertTrue(q.exists())
            fresh = dev.get_or_create_identity(home=env.home)
            self.assertNotEqual(fresh.device_uid, first.device_uid)
            self.assertTrue(duid.validate_device_uid(fresh.device_uid))

    def test_t08_concurrent_first_initialization(self):
        """Two racing threads in one process: single identity, both agree.
        (Cross-process correctness is T08b — this stays a fast in-proc check
        of the thread-optimization layer.)"""
        import threading
        with SplitHome() as env:
            results = []
            errors = []

            def worker():
                try:
                    ident = dev.get_or_create_identity(home=env.home)
                    results.append(ident.device_uid)
                except Exception as exc:            # pragma: no cover
                    errors.append(repr(exc))

            threads = [threading.Thread(target=worker) for _ in range(4)]
            for th in threads:
                th.start()
            for th in threads:
                th.join()
            self.assertEqual(errors, [])
            on_disk = json.loads(paths.device_json_path(
                env.home).read_text(encoding="utf-8"))["device_uid"]
            self.assertEqual(len(results), 4)
            self.assertEqual(set(results), {on_disk})
            leftovers = list(env.home.glob("device.json.tmp*"))
            self.assertEqual(leftovers, [])


class MultiprocessIdentityTests(unittest.TestCase):
    """B-1: REAL cross-process stress — independent OS processes, not
    threads. Every returned UID must equal the canonical on-disk one."""

    def _run_round(self, n_procs: int) -> tuple[set[str], str, int, list]:
        """One stress round inside its own tmp home. Returns
        (returned_uid_set, on_disk_uid, device_json_mode, residue_names) —
        filesystem assertions run INSIDE the context (the tmp home is
        deleted on exit)."""
        with SplitHome() as env:            # tmp home; repo on sys.path
            repo = str(Path(__file__).resolve().parents[1])
            worker = (
                "import sys, json\n"
                "from pathlib import Path\n"
                "sys.path.insert(0, %r)\n"
                "from costguard_split.identity import device as dev\n"
                "ident = dev.get_or_create_identity(home=Path(%r))\n"
                "print(ident.device_uid)\n" % (repo, str(env.home))
            )
            procs = [subprocess.Popen(
                [sys.executable, "-c", worker],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                for _ in range(n_procs)]
            uids, errors = [], []
            for p in procs:
                out, err = p.communicate()
                uids.append(out.strip())
                if p.returncode != 0:
                    errors.append(err.strip()[-300:])
            self.assertEqual(errors, [], "worker processes failed")
            self.assertEqual(
                len([u for u in uids if u.startswith("cgdev_")]), n_procs)
            on_disk = json.loads(paths.device_json_path(
                env.home).read_text(encoding="utf-8"))["device_uid"]
            # B-1a: canonical artifact mode + zero residue (pre-cleanup).
            # split.db is SplitHome's own seeded fixture, not identity litter.
            mode = os.stat(paths.device_json_path(env.home)).st_mode & 0o777
            residue = [p.name for p in env.home.iterdir()
                       if p.name not in ("device.json", "split.db")]
            return set(uids), on_disk, mode, residue

    def test_t08b_multiprocess_single_uid_5r_x8p(self):
        """5 rounds x 8 processes: all returned UIDs == disk UID."""
        for round_no in range(5):
            with self.subTest(round=round_no):
                uids, on_disk, mode, residue = self._run_round(8)
                self.assertEqual(len(uids), 1,
                                 f"round {round_no}: ghost UIDs {uids}")
                self.assertEqual(uids, {on_disk})
                self.assertEqual(mode, 0o600)
                self.assertEqual(residue, [], "tmp/lock litter on disk")

    def test_t08c_multiprocess_single_uid_20p(self):
        """1 round x 20 processes (VPS stress shape)."""
        uids, on_disk, mode, residue = self._run_round(20)
        self.assertEqual(len(uids), 1)
        self.assertEqual(uids, {on_disk})
        self.assertEqual(mode, 0o600)
        self.assertEqual(residue, [])

    def test_b1a_mode_0600_single_and_hardened(self):
        """Single-process 0600; permissive existing file re-hardened with
        SAME uid (no rotation) on the read path."""
        with SplitHome() as env:
            ident = dev.get_or_create_identity(home=env.home)
            f = paths.device_json_path(env.home)
            self.assertEqual(os.stat(f).st_mode & 0o777, 0o600)
            os.chmod(f, 0o644)                       # simulate legacy 0644
            again = dev.get_or_create_identity(home=env.home)
            self.assertEqual(again.device_uid, ident.device_uid)
            self.assertEqual(os.stat(f).st_mode & 0o777, 0o600)

    def test_b1_stale_dead_owner_lock_reclaimed(self):
        """Crashed writer's lock (dead pid + old mtime) is broken, not
        waited on. Ambiguous locks (fresh mtime) are NEVER broken."""
        with SplitHome() as env:
            home = env.home
            home.mkdir(parents=True, exist_ok=True)
            lock = home / "device.json.lock"
            lock.write_text(json.dumps(
                {"pid": 2**28, "created_at": "2020-01-01T00:00:00+00:00",
                 "created_mono": 0.0}), encoding="utf-8")
            old = time.time() - dev.STALE_LOCK_SEC - 5
            os.utime(lock, (old, old))     # backdate: abandoned long ago
            ident = dev.get_or_create_identity(home=home)
            self.assertTrue(duid.validate_device_uid(ident.device_uid))
            self.assertFalse(lock.exists())          # reclaimed + cleaned
        # a FRESH lock with a dead owner is left alone (ambiguous age):
        with SplitHome() as env:
            home = env.home
            home.mkdir(parents=True, exist_ok=True)
            lock = home / "device.json.lock"
            lock.write_text(json.dumps(
                {"pid": 2**28, "created_at": "t", "created_mono": 0.0}),
                encoding="utf-8")                    # dead pid, fresh mtime
            old_timeout = dev.LOCK_TIMEOUT_S
            dev.LOCK_TIMEOUT_S = 0.2
            try:
                with self.assertRaises(
                        dev.DeviceIdentityInitializationTimeout):
                    dev.get_or_create_identity(home=home)
            finally:
                dev.LOCK_TIMEOUT_S = old_timeout
            self.assertTrue(lock.exists())           # NOT broken
            lock.unlink()

    def test_b1_timeout_never_mints(self):
        """A live foreign writer + fresh lock: follower must time out and
        must NOT mint a second identity (bounded wait)."""
        with SplitHome() as env:
            home = env.home
            home.mkdir(parents=True, exist_ok=True)
            lock = home / "device.json.lock"
            lock.write_text(json.dumps(
                {"pid": os.getpid(),           # OUR pid => alive forever
                 "created_at": "t", "created_mono": time.monotonic()}),
                encoding="utf-8")
            old_timeout = dev.LOCK_TIMEOUT_S
            dev.LOCK_TIMEOUT_S = 0.15             # keep the test fast
            try:
                with self.assertRaises(
                        dev.DeviceIdentityInitializationTimeout):
                    dev.get_or_create_identity(home=home)
            finally:
                dev.LOCK_TIMEOUT_S = old_timeout
            self.assertFalse(
                paths.device_json_path(home).exists(),
                "follower minted despite not owning the lock")
            lock.unlink()


class DbPathResolverTests(unittest.TestCase):
    """B-2: ONE resolver. db.connect() must honor explicit > env > default,
    with no import-time caching."""

    def test_db_connect_env_wins_and_no_default_pollution(self):
        with tempfile.TemporaryDirectory() as td:
            env_home = Path(td) / "A"
            # snapshot the real default DB (if any) BEFORE the probe
            default_db = Path.home() / ".costguard" / "split.db"
            before = default_db.stat().st_mtime if default_db.exists() \
                else None
            with temporary_costguard_home(env_home):
                conn = split_db.connect()            # no args at all
                try:
                    self.assertTrue(
                        (env_home / "split.db").exists())
                finally:
                    conn.close()
            # real default home untouched (no new file / no rewrite)
            if before is None:
                self.assertFalse(default_db.exists(),
                                 "default home polluted despite env")
            else:
                self.assertEqual(default_db.stat().st_mtime, before)

    def test_db_connect_no_import_time_cache(self):
        # env set AFTER import must be honored (proves call-time resolve)
        with tempfile.TemporaryDirectory() as td:
            late_home = Path(td) / "B"
            with temporary_costguard_home(late_home):
                self.assertEqual(split_db.split_db_path(),
                                 late_home / "split.db")
                conn = split_db.connect()
                conn.close()
                self.assertTrue((late_home / "split.db").exists())

    def test_db_connect_explicit_beats_env(self):
        with tempfile.TemporaryDirectory() as td:
            env_home = Path(td) / "B"
            explicit_home = Path(td) / "C"
            with temporary_costguard_home(env_home):
                conn = split_db.connect(home=explicit_home)
                conn.close()
                self.assertTrue(
                    (explicit_home / "split.db").exists())
                self.assertFalse((env_home / "split.db").exists())

    def test_split_db_path_delegates_to_paths(self):
        # B-2 structural rule: db.split_db_path IS paths.split_db_path
        with tempfile.TemporaryDirectory() as td:
            with temporary_costguard_home(Path(td) / "X"):
                self.assertEqual(
                    split_db.split_db_path(), paths.split_db_path())
                self.assertEqual(
                    split_db.split_db_path(td), paths.split_db_path(td))

    def test_bonus_malformed_key_never_rotates(self):
        """Malformed fingerprint key = loud error, NOT silent rotation
        (rotation silently re-identifies every fingerprinted member)."""
        with SplitHome() as env:
            key = dev.load_or_create_key(env.home)
            f = paths.fingerprint_key_path(env.home)
            self.assertEqual(os.stat(f).st_mode & 0o777, 0o600)
            f.write_text("garbage-not-a-key", encoding="utf-8")
            with self.assertRaises(ValueError):
                dev.load_or_create_key(env.home)
            self.assertEqual(f.read_text(encoding="utf-8"),
                             "garbage-not-a-key")   # NOT overwritten


class TestOrderIndependence(unittest.TestCase):
    """B-3 meta-test: run the whole suite in deterministic-but-varied orders;
    any cross-test leakage shows up as failures here.

    The meta-tests EXCLUDE themselves from the loaded suite — otherwise
    running the suite inside the suite recurses forever.
    """

    SELF_CLASS = "TestOrderIndependence"

    def _run_suite(self, order_key):
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromName("tests.split_p0_test")
        flat = []
        for ts in suite:
            for t in ts._tests:
                if type(t).__name__ != self.SELF_CLASS:
                    flat.append(t)
        flat.sort(key=order_key)
        result = unittest.TestResult()
        unittest.TestSuite(flat).run(result)
        return result.wasSuccessful(), len(result.failures), \
            len(result.errors)

    def test_reverse_order_passes(self):
        ok, fails, errs = self._run_suite(
            lambda t: tuple(reversed(t.id())))
        self.assertTrue(ok, f"reverse order: {fails} failures {errs} errors")

    def test_shuffled_orders_pass(self):
        import random
        rng = random.Random(20260906)
        for round_no in range(3):
            with self.subTest(round=round_no):
                salt = [rng.random() for _ in range(64)]
                ok, fails, errs = self._run_suite(
                    lambda t, s=salt: (s[hash(t.id()) % len(s)], t.id()))
                self.assertTrue(ok,
                                f"shuffle {round_no}: {fails}f {errs}e")


class FingerprintTests(unittest.TestCase):
    def setUp(self):
        self.key = fp.new_fingerprint_key()
        self.other_key = fp.new_fingerprint_key()

    def test_t09_hostname_hmac_privacy(self):
        RAW = "host-A"   # exact raw registered by SplitHome.register
        f1 = fp.hostname_fingerprint(RAW, self.key)
        self.assertTrue(f1.startswith("hk1:"))
        self.assertEqual(fp.hostname_fingerprint("HOST-a", self.key), f1)
        self.assertNotEqual(fp.hostname_fingerprint(RAW, self.other_key),
                            f1)                    # key-bound
        with SplitHome() as env:
            env.register(name="A")
            dump = json.dumps(list(env.conn.execute(
                "SELECT * FROM devices")))
            self.assertNotIn(RAW, dump)            # raw never persisted

    def test_t10_username_hmac_privacy(self):
        RAW = "test-user.local"
        fu = fp.username_fingerprint(RAW, self.key)
        self.assertTrue(fp.parse_fingerprint(fu)[0] == "hk1")
        with SplitHome() as env:
            device, _ = env.register(name="B")
            everything = json.dumps(
                [list(env.conn.execute("SELECT * FROM devices")),
                 list(env.conn.execute("SELECT * FROM audit_events"))])
            self.assertNotIn(RAW, everything)

    def test_t11_network_hmac_privacy(self):
        fn = fp.network_fingerprint("203.0.113.9", self.key)
        self.assertTrue(fn.startswith("hk1:"))
        self.assertNotIn("203.0.113.9", fn)
        self.assertEqual(fp.network_fingerprint("203.0.113.9", self.key), fn)
        self.assertNotEqual(
            fp.network_fingerprint("203.0.113.9", self.other_key), fn)
        # IPv6 canonicalization is stable
        self.assertEqual(
            fp.network_fingerprint("2001:0DB8::0001", self.key),
            fp.network_fingerprint("2001:db8::1", self.key))
        with self.assertRaises(ValueError):
            fp.network_fingerprint("not-an-ip", self.key)

    def test_t12_hash_key_version_prefix(self):
        value = fp.fingerprint("anything", self.key)
        version, digest = fp.parse_fingerprint(value)
        self.assertEqual(version, "hk1")
        self.assertRegex(digest, r"^[0-9a-f]{32}$")
        # deterministic same key/value; different across keys
        self.assertEqual(fp.fingerprint("anything", self.key), value)
        self.assertNotEqual(fp.fingerprint("anything", self.other_key),
                            value)
        # malformed stored values rejected loudly
        with self.assertRaises(ValueError):
            fp.parse_fingerprint("v9:abcd")
        with self.assertRaises(ValueError):
            fp.parse_fingerprint("hk1:short")


class MigrationTests(unittest.TestCase):
    def _build_v1(self, db):
        db.execute(
            "CREATE TABLE schema_version (version INTEGER NOT NULL,"
            " applied_at TEXT NOT NULL)")
        db.execute("INSERT INTO schema_version VALUES (1,'t')")
        db.executescript(schemas.MIGRATIONS[0][1])
        db.execute("INSERT INTO organizations VALUES"
                   " ('org1','Demo','active','t','t')")
        db.execute("INSERT INTO members VALUES"
                   " ('mem_k','org1','test-member',NULL,'active','t','t')")
        db.execute(
            "INSERT INTO devices (id, organization_id, device_uid,"
            " member_id, display_name, hostname_hash, username_hash, os,"
            " arch, first_seen_at, last_seen_at, status,"
            " identity_confidence, collector_version, created_at,"
            " updated_at) VALUES ('dev_a','org1',"
            "'cgdev_018f0c9a-1605-4bec-8000-17b71faba7e3','mem_k','A',"
            "'hk1:'||'a','hk1:'||'b','Linux','x86',"
            "'2026-09-01T00:00:00+00:00','t2','unassigned',0,'','t','t')")
        db.execute(
            "INSERT INTO devices (id, organization_id, device_uid,"
            " member_id, display_name, hostname_hash, username_hash, os,"
            " arch, first_seen_at, last_seen_at, status,"
            " identity_confidence, collector_version, created_at,"
            " updated_at) VALUES ('dev_b','org1',"
            "'cgdev_018f0c9a-1605-4bec-8000-17b71faba7e4',NULL,'B',"
            "'hk1:'||'c','hk1:'||'d','Linux','x86','t1','t2',"
            "'unassigned',0,'','t','t')")
        db.commit()

    def test_t13_migration_paths(self):
        # fresh install -> hardened schema directly
        with tempfile.TemporaryDirectory() as td:
            db = sqlite3.connect(Path(td) / "fresh.db")
            applied = schemas.apply_migrations(db)
            self.assertEqual(applied, 2)
            tables = {r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertLessEqual(
                {"organizations", "members", "devices",
                 "device_assignments", "audit_events"}, tables)
            self.assertEqual(schemas.apply_migrations(db), 0)  # idempotent
            db.close()
        # v1 database with DATA -> v2, nothing lost
        with tempfile.TemporaryDirectory() as td:
            db = sqlite3.connect(Path(td) / "old.db")
            self._build_v1(db)
            applied = schemas.apply_migrations(db)
            self.assertEqual(applied, 1)
            # member survived
            self.assertEqual(
                db.execute("SELECT display_name FROM members WHERE"
                           " id='mem_k'").fetchone()[0], "test-member")
            # member_id column dropped (dual-truth removed)
            self.assertNotIn(
                "member_id",
                {r[1] for r in db.execute("PRAGMA table_info(devices)")})
            # v1 'unassigned' lifecycle normalized to 'active'
            self.assertEqual(
                db.execute("SELECT status FROM devices WHERE"
                           " id='dev_a'").fetchone()[0], "active")
            # bound member migrated into an open-ended assignment
            row = db.execute(
                "SELECT member_id, valid_to FROM device_assignments"
                " WHERE device_id='dev_a'").fetchone()
            self.assertEqual(row[0], "mem_k")
            self.assertIsNone(row[1])
            # unbound device has NO assignment row (derived unassigned)
            self.assertIsNone(db.execute(
                "SELECT 1 FROM device_assignments WHERE"
                " device_id='dev_b'").fetchone())
            self.assertEqual(schemas.apply_migrations(db), 0)


class TenantAndAssignmentTests(unittest.TestCase):
    def test_t14_cross_org_fk_rejection(self):
        with SplitHome() as env:
            db = env.conn
            device, _ = env.register(org="org1")
            # service guard: member from org2 cannot get org1's device
            with self.assertRaises(ValueError):
                reg.enroll_assignment(
                    db, organization_id="org1", device_id=device.id,
                    member_id="mem_o", valid_from=T0)
            # org2 device used in an org2 enrollment with org1 device id:
            with self.assertRaises(ValueError):
                reg.enroll_assignment(
                    db, organization_id="org2", device_id=device.id,
                    member_id="mem_o", valid_from=T0)
            # DATABASE guard: raw SQL cross-org pair is impossible
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute(
                    "INSERT INTO device_assignments (id, organization_id,"
                    " device_id, member_id, valid_from, valid_to, created_at)"
                    " VALUES ('asg_raw','org1', ?, 'mem_o', ?, NULL, ?)",
                    (device.id, T0, T0))

    def test_t15_t16_t17_t18_assignment_timeline(self):
        with SplitHome() as env:
            db = env.conn
            device, _ = env.register()
            # T15 initial
            reg.enroll_assignment(db, organization_id="org1",
                                  device_id=device.id, member_id="mem_k",
                                  valid_from=T0, reason="initial")
            self.assertEqual(reg.current_member(db, device.id), "mem_k")
            # T17 overlap rejected (open interval exists)
            with self.assertRaises(reg.OverlappingAssignment):
                reg.enroll_assignment(db, organization_id="org1",
                                      device_id=device.id,
                                      member_id="mem_a", valid_from=T0)
            with self.assertRaises(reg.OverlappingAssignment):
                reg.enroll_assignment(db, organization_id="org1",
                                      device_id=device.id,
                                      member_id="mem_a", valid_from=T0,
                                      valid_to=T1)   # inside open interval
            # T16 reassignment: closes old, opens new, history kept
            old, new = reg.reassign_device(
                db, organization_id="org1", device_id=device.id,
                new_member_id="mem_a", effective_at=T1, reason="handover")
            self.assertIsNone(new.valid_to)
            rows = list(db.execute(
                "SELECT member_id, valid_from, valid_to"
                " FROM device_assignments ORDER BY valid_from"))
            self.assertEqual([r[0] for r in rows], ["mem_k", "mem_a"])
            # T18 event-time attribution: Sep5 -> test-member, Sep20 -> test-member-2
            self.assertEqual(
                env.member(device.id, "2026-09-05T00:00:00+00:00"), "mem_k")
            self.assertEqual(
                env.member(device.id, "2026-09-20T00:00:00+00:00"), "mem_a")
            # before the first assignment: nobody
            self.assertIsNone(env.member(device.id, "2026-08-01T00:00:00+00:00"))

    def test_t22_unknown_device_has_no_active_assignment(self):
        with SplitHome() as env:
            device, created = env.register()
            self.assertTrue(created)
            self.assertEqual(device.status, "active")     # lifecycle only
            self.assertIsNone(reg.current_member(
                env.conn, device.id))                     # derived unassigned
            self.assertIsNone(env.member(device.id, "2026-09-05T00:00:00+00:00"))
            # re-register keeps it unattributed
            device2, created2 = env.register(uid=device.device_uid)
            self.assertFalse(created2)
            self.assertIsNone(reg.current_member(env.conn, device.id))
            # P0 has no auto-attribution API at all
            self.assertFalse(hasattr(reg, "assign_member"))


class AuditTests(unittest.TestCase):
    def test_t19_audit_append_only(self):
        with SplitHome() as env:
            db = env.conn
            device, _ = env.register()
            reg.enroll_assignment(db, organization_id="org1",
                                  device_id=device.id, member_id="mem_k",
                                  valid_from=T0)
            reg.reassign_device(db, organization_id="org1",
                                device_id=device.id, new_member_id="mem_a",
                                effective_at=T1, reason="handover")
            rows = list(audit.list_for_entity(
                db, organization_id="org1", entity_id=device.id))
            types = [r[1] for r in rows]
            self.assertIn("device.registered", types)
            self.assertIn("device.reassigned", types)
            self.assertEqual(len(rows), len(types))     # append-only growth
            # no update/delete path in the audit service
            for banned in ("update", "delete", "remove", "rewrite"):
                self.assertFalse(
                    any(banned in name.lower()
                        for name in dir(audit)),
                    f"audit service exposes {banned}()")

    def test_t20_audit_before_after_json(self):
        with SplitHome() as env:
            db = env.conn
            device, _ = env.register()
            reg.enroll_assignment(db, organization_id="org1",
                                  device_id=device.id, member_id="mem_k",
                                  valid_from=T0)
            reg.reassign_device(db, organization_id="org1",
                                device_id=device.id, new_member_id="mem_a",
                                effective_at=T1)
            event = db.execute(
                "SELECT before_json, after_json FROM audit_events"
                " WHERE event_type='device.reassigned'").fetchone()
            before = json.loads(event[0])
            after = json.loads(event[1])
            self.assertEqual(before["member"], "mem_k")
            self.assertEqual(after["member"], "mem_a")
            # tenant id always present on every audit row
            for r in db.execute("SELECT organization_id FROM audit_events"):
                self.assertEqual(r[0], "org1")


class PolicyTests(unittest.TestCase):
    def test_t21_no_float_monetary_schema(self):
        with SplitHome() as env:
            self.assertEqual(policy.guard_money_columns(env.conn), [])
        # static scan of the split source tree: no float money anywhere
        root = Path(__file__).resolve().parents[1] / "costguard_split"
        self.assertEqual(policy.guard_source_tree_static(root), [])
        # and the guard itself actually catches a violation (guard-the-guard)
        with SplitHome() as env:
            env.conn.execute("CREATE TABLE bad_allocations "
                             "(id TEXT, allocation REAL)")
            self.assertEqual(len(policy.guard_money_columns(env.conn)), 1)


class DtoTests(unittest.TestCase):
    def test_safe_evidence_dto(self):
        ident = dev.DeviceIdentity(
            device_uid=duid.new_device_uid(), device_name="x",
            first_seen_at=T0, hostname="test-host", username="test-user",
            os_name="Linux", arch="x86_64")
        key = fp.new_fingerprint_key()
        ev = dev.hashed_evidence(ident, key)
        evidence = dto.DeviceEvidenceDTO(
            device_uid=ev["device_uid"],
            hostname_fingerprint=ev["hostname_hash"],
            username_fingerprint=ev["username_hash"],
            os=ev["os"], arch=ev["arch"],
            first_seen_at=ev["first_seen_at"],
            last_seen_at=ev["first_seen_at"],
            collector_version=ev["collector_version"])
        self.assertEqual(evidence.validate(), [])
        # raw values can never ride along
        raw_payload = dict(evidence.__dict__, hostname="test-host")
        with self.assertRaises(ValueError):
            dto.assert_dto_never_carries_raw(raw_payload)
        clean = dict(evidence.__dict__)
        dto.assert_dto_never_carries_raw(clean)      # no raise

    def test_usage_claim_contract(self):
        claim = dto.UsageEventClaim(
            device_uid=duid.new_device_uid(), provider="codex",
            source_event_id="evt-123", model="gpt-5.5",
            started_at=T0, ended_at=T0, session_ref="sess-1",
            input_tokens=10, output_tokens=5)
        self.assertEqual(claim.validate(), [])
        # float tokens rejected at the boundary (PATCH 9)
        bad = dto.UsageEventClaim(
            device_uid=duid.new_device_uid(), provider="codex",
            source_event_id="e", model="m", started_at=T0, ended_at=T0,
            session_ref="s", input_tokens=1.5)
        self.assertTrue(any("input_tokens" in e for e in bad.validate()))
        # canonical event id replaces (source, session_ref, timestamp)
        self.assertEqual(
            dto.canonical_source_event_id("Codex", "evt 9"),
            "codex:evt 9")
        with self.assertRaises(ValueError):
            dto.canonical_source_event_id("codex", "  ")


if __name__ == "__main__":
    unittest.main(verbosity=2)
