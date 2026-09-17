"""P1A-08 test matrix slice: C3 plug-in isolation, M1 deep migration
survival, and the U*/I*/S*/C*/M*/X1 traceability index (spec section 12).

Adds no production code and modifies no existing test: C3 proves a new
provider needs zero core edits, M1 verifies P0 data survives v2->v3
field-by-field, and the index pins every matrix ID to a real unittest so
deleting any coverage fails here. Human-readable mapping: TEST_MATRIX.md.
"""

from __future__ import annotations

import importlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from costguard_split import db as split_db
from costguard_split.connectors import (
    BaseConnector,
    ConnectorRegistry,
    RawUsage,
)
from costguard_split.ingest.service import ingest_usage_event
from costguard_split.api.context import ServerContext
from costguard_split.schemas import tables as schemas

REPO_ROOT = Path(__file__).resolve().parents[1]

UID_A = "cgdev_018f0c9a-1605-4bec-8000-17b71faba7e1"
T0 = "2026-09-01T00:00:00+00:00"
T1 = "2026-09-10T00:00:00+00:00"

# spec section 12 matrix. Values: (module, case, method) that MUST exist,
# or "deferred:<reason>" for IDs explicitly outside this slice's gate.
MATRIX = {
    "U1": ("tests.split_p1a_claim_test", "UsageEventClaimBoundaryTests",
           "test_every_counter_rejects_bool_float_string_and_negative"),
    "U2": ("tests.split_p1a_claim_test", "UsageEventClaimBoundaryTests",
           "test_server_authority_money_and_private_fields_are_all_rejected"),
    "U3": ("tests.split_p1a_provider_test", "ClaudeConnectorTests",
           "test_normalize_maps_all_token_classes_and_identity"),
    "U4": ("tests.split_p1a_ingest_test", "UsageIngestTests",
           "test_missing_source_event_id_is_deterministic_and_payload_"
           "sensitive"),
    "U5": ("tests.split_p1a_ingest_test", "UsageIngestTests",
           "test_same_session_and_timestamp_with_distinct_event_ids_"
           "both_insert"),
    "I1": ("tests.split_api_usage_test", "SingleEventTests",
           "test_created_returns_201_and_event_shape"),
    "I2": ("tests.split_api_usage_test", "SingleEventTests",
           "test_duplicate_replay_returns_200_same_id"),
    "I3": ("tests.split_api_usage_test", "BatchTests",
           "test_mixed_results_partial_success"),
    "I4": ("tests.split_p1a_ingest_test", "UsageIngestTests",
           "test_member_is_derived_from_assignment_at_event_start"),
    "I5": ("tests.split_p1a_ingest_test", "UsageIngestTests",
           "test_unassigned_event_has_null_member"),
    "S1": ("tests.split_api_usage_test", "SingleEventTests",
           "test_forbidden_and_server_fields_are_422"),
    "S2": ("tests.split_api_usage_test", "SingleEventTests",
           "test_unknown_device_is_404_hidden_without_usage_write"),
    "S3": ("tests.split_api_usage_test", "ReadEventTests",
           "test_get_foreign_event_is_404_hidden"),
    "C1": ("tests.split_p1a_provider_test", "ClaudeConnectorTests",
           "test_normalize_maps_all_token_classes_and_identity"),
    "C2": ("tests.split_p1a_provider_test", "CodexConnectorTests",
           "test_discover_and_normalize_full_turn"),
    "C3": ("tests.split_p1a_matrix_test", "FakeProviderIsolationTests",
           "test_c3_new_provider_requires_no_core_edit"),
    "M1": ("tests.split_p1a_matrix_test", "MigrationSurvivalTests",
           "test_m1_p0_data_survives_v2_to_v3_field_by_field"),
    "M2": ("tests.split_p1a_schema_test", "SchemaV3Tests",
           "test_fresh_database_reaches_v3_and_repeat_is_noop"),
    "X1": ("tests.split_p1a_schema_test", "SchemaV3Tests",
           "test_migration_guard_rejects_all_float_money_types"),
    # Optional public price apply belongs to the P1A-2 slice; it must NOT
    # exist yet (pricing logic in P1A core is forbidden).
    "P1": "deferred:P1A-2 optional public price apply (feature-flagged)",
}

_CORE_TREES = ("costguard_split", "costguard_agent", "pricing")

FAKE_PROVIDER_SOURCE = '''
"""Dynamic FakeProvider used only by the C3 matrix test."""
import json
from pathlib import Path

from costguard_split.connectors import BaseConnector, RawUsage
from costguard_split.schemas.usage import UsageEventClaim


class FakeProvider(BaseConnector):
    name = "fakeprovider"

    def discover(self, home, since=None):
        for path in sorted(Path(home).glob("*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            yield RawUsage(payload=record)

    def normalize(self, raw):
        record = raw.payload
        return UsageEventClaim(
            device_uid=self.device_uid,
            provider=self.name,
            source_event_id=record["event_id"],
            model=record["model"],
            started_at=record["started_at"],
            ended_at=record["ended_at"],
            session_ref=record["session_ref"],
            input_tokens=record["input_tokens"],
            output_tokens=record["output_tokens"],
        )

    def native_event_id(self, raw):
        return raw.payload["event_id"]
'''


def _git(args):
    return subprocess.run(["git", *args], cwd=REPO_ROOT,
                          capture_output=True, text=True, check=True).stdout


def _core_tree_snapshot():
    tracked = _git(["ls-files", *_CORE_TREES])
    dirty = [line for line in
             _git(["status", "--porcelain", "--", *_CORE_TREES])
             .splitlines() if line.strip()]
    return tracked, dirty


class FakeProviderIsolationTests(unittest.TestCase):
    """C3: a brand-new provider plugs in with ZERO core-tree edits."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        self.db_path = self.home / "split.db"
        self._git_available = (REPO_ROOT / ".git").exists()

    def tearDown(self):
        self._tmp.cleanup()

    def _seed_and_ingest(self, claim):
        db = split_db.connect(path=self.db_path)
        try:
            db.execute(
                "INSERT OR IGNORE INTO organizations "
                "(id,name,status,created_at,"
                "updated_at) VALUES ('org-fp','FP','active','t','t')")
            db.execute(
                "INSERT OR IGNORE INTO devices (id,organization_id,"
                "device_uid,"
                "display_name,hostname_hash,username_hash,os,arch,"
                "first_seen_at,last_seen_at,status,identity_confidence,"
                "collector_version,created_at,updated_at) "
                "VALUES ('dev-fp','org-fp',?,'d','hk1:a','hk1:b','Linux',"
                "'x86_64','t','t','active',0,'','t','t')", (UID_A,))
            db.commit()
            return ingest_usage_event(
                db, context=ServerContext("org-fp", "matrix"), claim=claim)
        finally:
            db.close()

    def test_c3_new_provider_requires_no_core_edit(self):
        if not self._git_available:
            self.skipTest("not inside a git worktree")
        before = _core_tree_snapshot()

        provider_file = self.home / "fake_provider.py"
        provider_file.write_text(FAKE_PROVIDER_SOURCE, encoding="utf-8")
        spec = importlib.util.spec_from_file_location(
            "fake_provider_matrix_c3", provider_file)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
            FakeProvider = module.FakeProvider

            # Registers into a plain registry: no core factory edit.
            registry = ConnectorRegistry()
            registry.register(FakeProvider.name, FakeProvider)
            self.assertIs(registry.get("fakeprovider"), FakeProvider)
            self.assertNotIn("fakeprovider",
                             __import__("costguard_split.connectors",
                                        fromlist=["default_registry"])
                             .default_registry().providers())

            # End-to-end: discover -> normalize -> ingest (created+duplicate)
            (self.home / "event-1.json").write_text(json.dumps({
                "event_id": "fp-1", "model": "fake-model",
                "started_at": T0, "ended_at": T1,
                "session_ref": "fp-session", "input_tokens": 7,
                "output_tokens": 9}), encoding="utf-8")
            connector = FakeProvider(device_uid=UID_A)
            raws = list(connector.discover(self.home))
            self.assertEqual(len(raws), 1)
            claim = connector.normalize(raws[0])
            # the SERVER canonicalizes the native id (claude:native shape);
            # the claim itself carries the raw provider-native value.
            self.assertEqual(claim.source_event_id, "fp-1")
            first = self._seed_and_ingest(claim)
            self.assertEqual(first.status, "created")
            replay = self._seed_and_ingest(claim)
            self.assertEqual(replay.status, "duplicate")
            self.assertEqual(replay.event.id, first.event.id)
        finally:
            sys.modules.pop(spec.name, None)

        after = _core_tree_snapshot()
        self.assertEqual(after, before,
                         "adding a provider changed the core tree")

    def test_core_tree_is_clean_baseline_for_c3(self):
        # The C3 comparison is only meaningful from a clean core tree;
        # uncommitted core edits would hide a real violation.
        if not self._git_available:
            self.skipTest("not inside a git worktree")
        _, dirty = _core_tree_snapshot()
        self.assertEqual(
            dirty, [],
            f"core trees have uncommitted changes: {dirty}")


class MigrationSurvivalTests(unittest.TestCase):
    """M1 deep: v1 P0 rows survive v1->v2->v3 field-by-field."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = sqlite3.connect(Path(self._tmp.name) / "m1.db")
        self.db.executescript(schemas.MIGRATIONS[0][1])     # v1 schema
        self.db.execute(
            "CREATE TABLE schema_version "
            "(version INTEGER NOT NULL, applied_at TEXT NOT NULL)")
        self._seed_v1_data()

    def tearDown(self):
        self.db.close()
        self._tmp.cleanup()

    def _seed_v1_data(self):
        db = self.db
        db.executescript("""
INSERT INTO organizations (id,name,status,created_at,updated_at) VALUES
    ('org-a','Alpha','active','2026-08-01T09:00:00+00:00',
     '2026-08-01T09:00:00+00:00'),
    ('org-b','Beta','disabled','2026-08-02T09:00:00+00:00',
     '2026-08-03T09:00:00+00:00');
INSERT INTO members (id,organization_id,display_name,email_optional,status,
    created_at,updated_at) VALUES
    ('mem-a1','org-a','Alice','alice@x.test','active',
     '2026-08-01T10:00:00+00:00','2026-08-01T10:00:00+00:00'),
    ('mem-a2','org-a','Bob',NULL,'disabled',
     '2026-08-01T11:00:00+00:00','2026-08-02T11:00:00+00:00'),
    ('mem-b1','org-b','Cara',NULL,'active',
     '2026-08-02T10:00:00+00:00','2026-08-02T10:00:00+00:00');
INSERT INTO devices (id,organization_id,device_uid,member_id,display_name,
    hostname_hash,username_hash,last_network_hash,os,arch,first_seen_at,
    last_seen_at,status,identity_confidence,collector_version,created_at,
    updated_at) VALUES
    ('dev-assigned','org-a','cgdev_018f0c9a-1605-4bec-8000-17b71faba7e1',
     'mem-a1','Laptop A','hk1:'||hex(zeroblob(16))||'','hk1:x',NULL,
     'Linux','x86_64','2026-08-05T08:00:00+00:00',
     '2026-08-06T08:00:00+00:00','active',42,'v0.9',
     '2026-08-05T08:00:00+00:00','2026-08-06T08:00:00+00:00'),
    ('dev-legacy-unassigned','org-a',
     'cgdev_018f0c9a-1605-4bec-8000-17b71faba7e2',
     NULL,'Laptop B','hk1:'||hex(zeroblob(16))||'','hk1:y','hk1:z',
     'Darwin','arm64','2026-08-07T08:00:00+00:00',
     '2026-08-08T08:00:00+00:00','unassigned',7,'v0.9',
     '2026-08-07T08:00:00+00:00','2026-08-08T08:00:00+00:00'),
    ('dev-retired','org-b',
     'cgdev_018f0c9a-1605-4bec-8000-17b71faba7e3',
     'mem-b1','Laptop C','hk1:'||hex(zeroblob(16))||'','hk1:w',NULL,
     'Linux','x86_64','2026-08-09T08:00:00+00:00',
     '2026-08-10T08:00:00+00:00','retired',90,'v0.8',
     '2026-08-09T08:00:00+00:00','2026-08-10T08:00:00+00:00');
INSERT INTO audit_events (id,organization_id,actor_id,event_type,
    entity_type,entity_id,before_json,after_json,reason,created_at) VALUES
    ('aud-1','org-a','system','device.registered','device','dev-assigned',
     NULL,'{"device_uid":"cgdev_018f0c9a-1605-4bec-8000-17b71faba7e1"}',
     'initial','2026-08-05T08:00:00+00:00'),
    ('aud-2','org-b','mem-b1','member.created','member','mem-b1',
     NULL,'{"display_name":"Cara"}','onboarding',
     '2026-08-02T10:00:00+00:00');
""")
        db.commit()

    def _rows(self, sql):
        cursor = self.db.execute(sql)
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def test_m1_p0_data_survives_v2_to_v3_field_by_field(self):
        before = {
            "organizations": self._rows("SELECT * FROM organizations"),
            "members": self._rows("SELECT * FROM members"),
            "devices": self._rows(
                "SELECT * FROM devices ORDER BY id"),
            "audit_events": self._rows(
                "SELECT * FROM audit_events ORDER BY id"),
        }

        # v2 rebuilds devices (drops member_id, maps 'unassigned'->'active')
        # and derives the initial assignment from v1 devices.member_id.
        self.assertEqual(schemas.apply_migrations(self.db), 3)

        after_orgs = self._rows("SELECT * FROM organizations")
        self.assertEqual(after_orgs, before["organizations"])

        after_members = self._rows("SELECT * FROM members")
        self.assertEqual(after_members, before["members"])

        after_audits = self._rows("SELECT * FROM audit_events ORDER BY id")
        self.assertEqual(after_audits, before["audit_events"])

        after_devices = {
            row["id"]: row for row in
            self._rows("SELECT * FROM devices")}
        self.assertEqual(sorted(after_devices), sorted(before_devices_ids := [
            row["id"] for row in before["devices"]]))
        for old in before["devices"]:
            new = after_devices[old["id"]]
            for column, value in old.items():
                if column == "member_id":
                    # dual-truth column: dropped, replaced by the timeline
                    self.assertNotIn("member_id", new)
                    continue
                if column == "status" and value == "unassigned":
                    self.assertEqual(new["status"], "active")
                    continue
                self.assertEqual(
                    new[column], value,
                    f"devices.{column} lost for {old['id']}")
        # explicit legacy-status expectation beyond the loop above
        self.assertEqual(
            after_devices["dev-legacy-unassigned"]["status"], "active")
        self.assertEqual(after_devices["dev-retired"]["status"], "retired")

        assignments = {
            row["device_id"]: row for row in
            self._rows("SELECT * FROM device_assignments")}
        # one assignment per v1 device that had member_id, none without
        self.assertEqual(sorted(assignments),
                         ["dev-assigned", "dev-retired"])
        derived = assignments["dev-assigned"]
        self.assertEqual(derived["organization_id"], "org-a")
        self.assertEqual(derived["member_id"], "mem-a1")
        self.assertEqual(derived["valid_from"],
                         after_devices["dev-assigned"]["first_seen_at"])
        self.assertIsNone(derived["valid_to"])
        self.assertNotIn("dev-legacy-unassigned", assignments)

        # v3 usage layer exists on the migrated DB; its composite FKs still
        # enforce tenancy (cross-org usage insert is impossible) — with the
        # same foreign_keys=ON pragma the production connect() uses.
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.execute(
            "INSERT INTO usage_events (id,organization_id,device_id,"
            "device_uid,provider,model,session_ref,source_event_id,"
            "started_at,ended_at,received_at,created_at) VALUES "
            "('uev-m1','org-a','dev-assigned',"
            "'cgdev_018f0c9a-1605-4bec-8000-17b71faba7e1','claude','m',"
            "'s','claude:m1','t','t','t','t')")
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "INSERT INTO usage_events (id,organization_id,device_id,"
                "device_uid,provider,model,session_ref,source_event_id,"
                "started_at,ended_at,received_at,created_at) VALUES "
                "('uev-m1x','org-b','dev-assigned',"
                "'cgdev_018f0c9a-1605-4bec-8000-17b71faba7e1','claude','m',"
                "'s','claude:m1x','t','t','t','t')")


class MatrixIndexTests(unittest.TestCase):
    """Every spec-12 ID must resolve to a real, existing unittest."""

    def test_matrix_index_resolves_every_id(self):
        modules = {}
        cases = {}
        for matrix_id, entry in sorted(MATRIX.items()):
            with self.subTest(matrix_id=matrix_id):
                if isinstance(entry, str):
                    self.assertTrue(
                        entry.startswith("deferred:"),
                        f"{matrix_id}: free-text entry must be deferred")
                    continue
                module_name, case_name, method_name = entry
                module = modules.get(module_name)
                if module is None:
                    module = importlib.import_module(module_name)
                    modules[module_name] = module
                case = getattr(module, case_name, None)
                self.assertIsNotNone(
                    case, f"{matrix_id}: missing case {case_name}")
                method = getattr(case, method_name, None)
                self.assertIsNotNone(
                    method, f"{matrix_id}: missing test {method_name}")
                self.assertTrue(callable(method))

    def test_matrix_covers_every_p1a_gate_id(self):
        self.assertEqual(
            {matrix_id for matrix_id in MATRIX
             if not str(MATRIX[matrix_id]).startswith("deferred:")},
            {"U1", "U2", "U3", "U4", "U5",
             "I1", "I2", "I3", "I4", "I5",
             "S1", "S2", "S3", "C1", "C2", "C3", "M1", "M2", "X1"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
