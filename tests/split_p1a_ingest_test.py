"""P1A-03 usage ingestion service tests.

Service-level only: no HTTP and no provider connectors. Every identity and
usage fact is synthetic; each test owns a temporary SQLite database.
"""

from __future__ import annotations

import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from costguard_split import db as split_db
from costguard_split.api.context import ServerContext, TenantViolation
from costguard_split.ingest.service import (
    IngestConflict,
    IngestResult,
    ingest_usage_event,
)
from costguard_split.schemas.usage import UsageEventClaim

T0 = "2026-09-01T00:00:00+00:00"
T1 = "2026-09-10T00:00:00+00:00"
T2 = "2026-09-20T00:00:00+00:00"
T3 = "2026-09-30T00:00:00+00:00"
UID_A = "cgdev_018f0c9a-1605-4bec-8000-17b71faba7e1"
UID_B = "cgdev_018f0c9a-1605-4bec-8000-17b71faba7e2"


def claim(**overrides) -> UsageEventClaim:
    values = {
        "device_uid": UID_A,
        "provider": "Claude",
        "source_event_id": "native-a",
        "model": "test-model",
        "started_at": T1,
        "ended_at": T2,
        "session_ref": "session-a",
        "input_tokens": 10,
        "cached_input_tokens": 20,
        "cache_write_tokens": 30,
        "output_tokens": 40,
        "reasoning_tokens": 50,
        "request_count": 1,
        "provider_account_ref": "account-a",
        "collector_version": "test-collector",
        "source_type": "connector",
    }
    values.update(overrides)
    return UsageEventClaim(**values)


class UsageIngestTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "split.db"
        self.db = split_db.connect(path=self.db_path)
        self.ctx_a = ServerContext("org-a", "actor-a")
        self.ctx_b = ServerContext("org-b", "actor-b")
        self._seed_identity()

    def tearDown(self):
        self.db.close()
        self._tmp.cleanup()

    def _seed_identity(self):
        self.db.executemany(
            "INSERT INTO organizations (id,name,status,created_at,updated_at) "
            "VALUES (?,?,'active','t','t')",
            (("org-a", "Test A"), ("org-b", "Test B")),
        )
        self.db.executemany(
            "INSERT INTO members "
            "(id,organization_id,display_name,status,created_at,updated_at) "
            "VALUES (?,?,'Test Member','active','t','t')",
            (("mem-old", "org-a"), ("mem-new", "org-a"),
             ("mem-other", "org-b")),
        )
        for device_id, org, uid in (
                ("dev-a", "org-a", UID_A), ("dev-b", "org-b", UID_B)):
            self.db.execute(
                "INSERT INTO devices "
                "(id,organization_id,device_uid,display_name,hostname_hash,"
                "username_hash,os,arch,first_seen_at,last_seen_at,status,"
                "identity_confidence,collector_version,created_at,updated_at) "
                "VALUES (?,?,?,'Test Device','hk1:a','hk1:b','Linux','x86_64',"
                "?,?,'active',0,'','t','t')",
                (device_id, org, uid, T0, T3),
            )
        self.db.executemany(
            "INSERT INTO device_assignments "
            "(id,organization_id,device_id,member_id,valid_from,valid_to,"
            "created_at) VALUES (?,?,?,?,?,?,?)",
            (("asg-old", "org-a", "dev-a", "mem-old", T0, T2, T0),
             ("asg-new", "org-a", "dev-a", "mem-new", T2, None, T2)),
        )
        self.db.commit()

    def _usage_rows(self):
        return self.db.execute(
            "SELECT id,member_id,provider,source_event_id,input_tokens,"
            "pricing_version,api_equivalent_cost_usd FROM usage_events "
            "ORDER BY created_at,id").fetchall()

    def _audits(self):
        return self.db.execute(
            "SELECT event_type,entity_id,before_json,after_json FROM "
            "audit_events WHERE event_type LIKE 'usage.%' ORDER BY rowid"
        ).fetchall()

    def test_normal_ingest_injects_server_fields_and_null_money(self):
        result = ingest_usage_event(self.db, context=self.ctx_a, claim=claim())
        self.assertIsInstance(result, IngestResult)
        self.assertEqual(result.status, "created")
        event = result.event
        self.assertTrue(event.id.startswith("uev_"))
        self.assertEqual(event.organization_id, "org-a")
        self.assertEqual(event.device_id, "dev-a")
        self.assertEqual(event.member_id, "mem-old")
        self.assertEqual(event.provider, "claude")
        self.assertEqual(event.source_event_id, "claude:native-a")
        self.assertEqual(event.received_at, event.created_at)
        self.assertIsNone(event.pricing_version)
        self.assertIsNone(event.api_equivalent_cost_usd)
        self.assertEqual(self._usage_rows()[0][5:], (None, None))
        self.assertEqual(self._audits()[0][0], "usage.ingested")

    def test_cross_tenant_device_is_hidden_and_rejected_without_usage(self):
        with self.assertRaises(TenantViolation):
            ingest_usage_event(
                self.db, context=self.ctx_a, claim=claim(device_uid=UID_B))
        self.assertEqual(self._usage_rows(), [])
        self.assertEqual([row[0] for row in self._audits()], ["usage.rejected"])

    def test_identical_replay_is_duplicate_and_does_not_mutate_event(self):
        first = ingest_usage_event(self.db, context=self.ctx_a, claim=claim())
        before = self.db.execute(
            "SELECT * FROM usage_events WHERE id=?", (first.event.id,)
        ).fetchone()
        second = ingest_usage_event(self.db, context=self.ctx_a, claim=claim())
        after = self.db.execute(
            "SELECT * FROM usage_events WHERE id=?", (first.event.id,)
        ).fetchone()
        self.assertEqual(second.status, "duplicate")
        self.assertEqual(second.event.id, first.event.id)
        self.assertEqual(after, before)
        self.assertEqual(len(self._usage_rows()), 1)
        self.assertEqual([row[0] for row in self._audits()],
                         ["usage.ingested", "usage.duplicate"])

    def test_same_identity_different_payload_conflicts_without_update(self):
        first = ingest_usage_event(self.db, context=self.ctx_a, claim=claim())
        before = self.db.execute(
            "SELECT * FROM usage_events WHERE id=?", (first.event.id,)
        ).fetchone()
        with self.assertRaises(IngestConflict):
            ingest_usage_event(
                self.db, context=self.ctx_a, claim=claim(output_tokens=41))
        after = self.db.execute(
            "SELECT * FROM usage_events WHERE id=?", (first.event.id,)
        ).fetchone()
        self.assertEqual(after, before)
        self.assertEqual(len(self._usage_rows()), 1)
        self.assertEqual([row[0] for row in self._audits()],
                         ["usage.ingested", "usage.rejected"])

    def test_unexpected_audit_failure_rolls_back_usage_insert(self):
        with patch("costguard_split.ingest.service.audit.record",
                   side_effect=RuntimeError("synthetic audit failure")):
            with self.assertRaisesRegex(RuntimeError, "synthetic audit failure"):
                ingest_usage_event(self.db, context=self.ctx_a, claim=claim())
        self.assertEqual(self._usage_rows(), [])
        self.assertEqual(self._audits(), [])

    def test_insert_failure_does_not_leave_audit(self):
        self.db.execute("DROP TRIGGER IF EXISTS reject_usage")
        self.db.execute(
            "CREATE TRIGGER reject_usage BEFORE INSERT ON usage_events "
            "BEGIN SELECT RAISE(ABORT, 'synthetic insert failure'); END")
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            ingest_usage_event(self.db, context=self.ctx_a, claim=claim())
        self.assertEqual(self._usage_rows(), [])
        self.assertEqual(self._audits(), [])

    def test_member_is_derived_from_assignment_at_event_start(self):
        before = ingest_usage_event(
            self.db, context=self.ctx_a,
            claim=claim(source_event_id="before", started_at=T0, ended_at=T1))
        at_boundary = ingest_usage_event(
            self.db, context=self.ctx_a,
            claim=claim(source_event_id="at", started_at=T2, ended_at=T3))
        after = ingest_usage_event(
            self.db, context=self.ctx_a,
            claim=claim(source_event_id="after", started_at=T3, ended_at=T3))
        self.assertEqual(before.event.member_id, "mem-old")
        self.assertEqual(at_boundary.event.member_id, "mem-new")
        self.assertEqual(after.event.member_id, "mem-new")

    def test_unassigned_event_has_null_member(self):
        result = ingest_usage_event(
            self.db, context=self.ctx_b,
            claim=claim(device_uid=UID_B, source_event_id="unassigned"))
        self.assertIsNone(result.event.member_id)
        self.assertIsNone(self.db.execute(
            "SELECT member_id FROM usage_events WHERE id=?",
            (result.event.id,)).fetchone()[0])

    def test_same_session_and_timestamp_with_distinct_event_ids_both_insert(self):
        first = ingest_usage_event(
            self.db, context=self.ctx_a, claim=claim(source_event_id="event-a"))
        second = ingest_usage_event(
            self.db, context=self.ctx_a, claim=claim(source_event_id="event-b"))
        self.assertEqual((first.status, second.status), ("created", "created"))
        self.assertEqual(len(self._usage_rows()), 2)

    def test_missing_source_event_id_is_deterministic_and_payload_sensitive(self):
        first_claim = claim(source_event_id=None)
        first = ingest_usage_event(self.db, context=self.ctx_a,
                                   claim=first_claim)
        replay = ingest_usage_event(self.db, context=self.ctx_a,
                                    claim=first_claim)
        changed = ingest_usage_event(
            self.db, context=self.ctx_a,
            claim=claim(source_event_id=None, output_tokens=41))
        self.assertEqual(replay.status, "duplicate")
        self.assertEqual(replay.event.id, first.event.id)
        self.assertNotEqual(changed.event.source_event_id,
                            first.event.source_event_id)
        self.assertEqual(len(self._usage_rows()), 2)

    def test_concurrent_identical_replays_converge_to_one_event(self):
        self.db.close()
        barrier = threading.Barrier(2)
        results = []
        errors = []

        def worker():
            db = split_db.connect(path=self.db_path, check_same_thread=False)
            try:
                barrier.wait()
                results.append(ingest_usage_event(
                    db, context=self.ctx_a, claim=claim()))
            except Exception as exc:
                errors.append(exc)
            finally:
                db.close()

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.db = split_db.connect(path=self.db_path)
        self.assertEqual(errors, [])
        self.assertEqual(sorted(result.status for result in results),
                         ["created", "duplicate"])
        self.assertEqual(len({result.event.id for result in results}), 1)
        self.assertEqual(len(self._usage_rows()), 1)

    def test_audit_payload_is_allowlisted_and_contains_no_raw_content(self):
        ingest_usage_event(self.db, context=self.ctx_a, claim=claim())
        blob = " ".join(str(value or "") for row in self._audits()
                        for value in row).lower()
        for forbidden in ("prompt", "response", "content", "hostname",
                          "username", "raw_ip", "public_ip", "local_ip",
                          "secret", "account-a"):
            self.assertNotIn(forbidden, blob)


if __name__ == "__main__":
    unittest.main(verbosity=2)
