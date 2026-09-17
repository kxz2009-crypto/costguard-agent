"""P1A-01 canonical UsageEvent and schema-v3 migration tests.

All fixtures are synthetic and every database is temporary. This slice tests
only the domain model and storage schema; no ingest/API/connector behavior.
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from costguard_split.models.usage import UsageEvent
from costguard_split.schemas import policy
from costguard_split.schemas import tables as schemas

T0 = "2026-09-01T00:00:00+00:00"
T1 = "2026-09-01T00:00:01+00:00"
UID_A = "cgdev_018f0c9a-1605-4bec-8000-17b71faba7e1"
UID_B = "cgdev_018f0c9a-1605-4bec-8000-17b71faba7e2"


def usage_event(**overrides) -> UsageEvent:
    values = {
        "id": "uev-1",
        "organization_id": "org-a",
        "device_id": "dev-a",
        "device_uid": UID_A,
        "member_id": "mem-a",
        "provider": "claude",
        "provider_account_ref": None,
        "model": "test-model",
        "session_ref": "session-a",
        "source_event_id": "claude:event-a",
        "started_at": T0,
        "ended_at": T1,
        "received_at": T1,
        "input_tokens": 10,
        "cached_input_tokens": 20,
        "cache_write_tokens": 30,
        "output_tokens": 40,
        "reasoning_tokens": 50,
        "request_count": 1,
        "pricing_version": None,
        "api_equivalent_cost_usd": None,
        "source_type": "connector",
        "collector_version": "test-collector",
        "created_at": T1,
    }
    values.update(overrides)
    return UsageEvent(**values)


class UsageEventDomainTests(unittest.TestCase):
    def test_complete_event_preserves_five_token_classes(self):
        event = usage_event()
        self.assertEqual(
            (event.input_tokens, event.cached_input_tokens,
             event.cache_write_tokens, event.output_tokens,
             event.reasoning_tokens, event.request_count),
            (10, 20, 30, 40, 50, 1),
        )
        self.assertIsNone(event.pricing_version)
        self.assertIsNone(event.api_equivalent_cost_usd)

    def test_each_token_rejects_bool_float_and_negative_values(self):
        for field in (
                "input_tokens", "cached_input_tokens", "cache_write_tokens",
                "output_tokens", "reasoning_tokens"):
            for invalid, error in ((True, TypeError), (1.5, TypeError),
                                   (-1, ValueError)):
                with self.subTest(field=field, invalid=invalid):
                    with self.assertRaisesRegex(error, field):
                        usage_event(**{field: invalid})

    def test_request_count_must_be_non_negative_int(self):
        for invalid, error in ((False, TypeError), (1.0, TypeError),
                               (-1, ValueError)):
            with self.subTest(invalid=invalid):
                with self.assertRaises(error):
                    usage_event(request_count=invalid)


class SchemaV3Tests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "split.db"

    def tearDown(self):
        self._tmp.cleanup()

    def _connect(self):
        db = sqlite3.connect(self.path)
        db.execute("PRAGMA foreign_keys = ON")
        return db

    @staticmethod
    def _seed_v2(db):
        db.execute(
            "CREATE TABLE schema_version (version INTEGER NOT NULL, "
            "applied_at TEXT NOT NULL)"
        )
        db.executescript(schemas.MIGRATIONS[0][1])
        schemas._migrate_v2(db)
        db.execute("INSERT INTO schema_version VALUES (1, 't')")
        db.execute("INSERT INTO schema_version VALUES (2, 't')")
        db.commit()

    @staticmethod
    def _seed_identity(db):
        db.execute(
            "INSERT INTO organizations "
            "(id,name,status,created_at,updated_at) VALUES "
            "('org-a','Test A','active','t','t'),"
            "('org-b','Test B','active','t','t')"
        )
        for member_id, org in (("mem-a", "org-a"), ("mem-b", "org-b")):
            db.execute(
                "INSERT INTO members "
                "(id,organization_id,display_name,status,created_at,updated_at) "
                "VALUES (?,?,'Test Member','active','t','t')",
                (member_id, org),
            )
        for device_id, org, uid in (
                ("dev-a", "org-a", UID_A), ("dev-b", "org-b", UID_B)):
            db.execute(
                "INSERT INTO devices "
                "(id,organization_id,device_uid,display_name,hostname_hash,"
                "username_hash,os,arch,first_seen_at,last_seen_at,status,"
                "identity_confidence,collector_version,created_at,updated_at) "
                "VALUES (?,?,?,'Test Device','hk1:a','hk1:b','Linux','x86_64',"
                "?,?,'active',0,'','t','t')",
                (device_id, org, uid, T0, T1),
            )
        db.commit()

    @staticmethod
    def _insert_usage(db, **overrides):
        row = {
            "id": "uev-1", "organization_id": "org-a",
            "device_id": "dev-a", "device_uid": UID_A,
            "member_id": "mem-a", "provider": "claude",
            "model": "test-model", "session_ref": "session-a",
            "source_event_id": "claude:event-a", "started_at": T0,
            "ended_at": T1, "received_at": T1, "input_tokens": 1,
            "cached_input_tokens": 2, "cache_write_tokens": 3,
            "output_tokens": 4, "reasoning_tokens": 5,
            "request_count": 1, "source_type": "connector",
            "collector_version": "test-collector", "created_at": T1,
        }
        row.update(overrides)
        columns = tuple(row)
        db.execute(
            f"INSERT INTO usage_events ({','.join(columns)}) VALUES "
            f"({','.join('?' for _ in columns)})",
            tuple(row.values()),
        )

    def test_fresh_database_reaches_v3_and_repeat_is_noop(self):
        db = self._connect()
        self.assertEqual(schemas.apply_migrations(db), 3)
        self.assertEqual(
            db.execute("SELECT MAX(version) FROM schema_version").fetchone()[0],
            3,
        )
        self.assertEqual(schemas.apply_migrations(db), 0)
        db.close()

    def test_v2_upgrades_to_v3_without_losing_p0_data(self):
        db = self._connect()
        self._seed_v2(db)
        self._seed_identity(db)
        before = {
            table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("organizations", "members", "devices")
        }
        self.assertEqual(schemas.apply_migrations(db), 1)
        after = {
            table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in before
        }
        self.assertEqual(after, before)
        self.assertEqual(schemas.apply_migrations(db), 0)
        db.close()

    def test_usage_columns_indexes_and_numeric_types(self):
        db = self._connect()
        schemas.apply_migrations(db)
        columns = {row[1]: row[2].upper()
                   for row in db.execute("PRAGMA table_info(usage_events)")}
        token_fields = (
            "input_tokens", "cached_input_tokens", "cache_write_tokens",
            "output_tokens", "reasoning_tokens", "request_count",
        )
        self.assertTrue(all(columns[name] == "INTEGER" for name in token_fields))
        self.assertEqual(columns["api_equivalent_cost_usd"], "TEXT")
        self.assertEqual(columns["pricing_version"], "TEXT")
        indexes = {row[1] for row in db.execute("PRAGMA index_list(usage_events)")}
        self.assertLessEqual(
            {"idx_usage_org_time", "idx_usage_device_time",
             "idx_usage_member_time"}, indexes)
        self.assertEqual(policy.guard_money_columns(db), [])
        db.close()

    def test_migration_guard_rejects_all_float_money_types(self):
        for declared_type in ("REAL", "FLOAT", "DOUBLE"):
            with self.subTest(declared_type=declared_type):
                db = sqlite3.connect(":memory:")
                schemas.apply_migrations(db)
                db.execute(
                    f"CREATE TABLE bad_money (estimated_cost {declared_type})")
                with self.assertRaisesRegex(RuntimeError, declared_type):
                    schemas.apply_migrations(db)
                db.close()

    def test_identity_unique_but_same_timestamp_distinct_event_is_allowed(self):
        db = self._connect()
        schemas.apply_migrations(db)
        self._seed_identity(db)
        self._insert_usage(db)
        db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self._insert_usage(db, id="uev-duplicate")
        db.rollback()
        self._insert_usage(db, id="uev-2",
                           source_event_id="claude:event-b")
        db.commit()
        self.assertEqual(
            db.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0], 2)
        db.close()

    def test_composite_device_and_member_foreign_keys_enforce_tenant(self):
        db = self._connect()
        schemas.apply_migrations(db)
        self._seed_identity(db)
        with self.assertRaises(sqlite3.IntegrityError):
            self._insert_usage(db, device_id="dev-b")
        db.rollback()
        with self.assertRaises(sqlite3.IntegrityError):
            self._insert_usage(db, member_id="mem-b")
        db.rollback()
        self._insert_usage(db, member_id=None)
        db.commit()
        db.close()

    def test_database_rejects_each_negative_counter(self):
        fields = (
            "input_tokens", "cached_input_tokens", "cache_write_tokens",
            "output_tokens", "reasoning_tokens", "request_count",
        )
        db = self._connect()
        schemas.apply_migrations(db)
        self._seed_identity(db)
        for index, field in enumerate(fields):
            with self.subTest(field=field):
                with self.assertRaises(sqlite3.IntegrityError):
                    self._insert_usage(
                        db, id=f"uev-negative-{index}",
                        source_event_id=f"claude:negative-{index}",
                        **{field: -1},
                    )
                db.rollback()
        db.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
