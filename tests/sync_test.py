"""Sync-preparation tests (SaaS Integration Preparation, Task 4).

Run: python -m tests.sync_test
Covers:
  S1  export payload validates against the schema allowlist
  S2  payloads (export + DTO) contain no privacy fields
  S3  sync is default OFF and performs no network I/O
  S4  device identity is local, anonymous, stable
"""

from __future__ import annotations

import io
import json
import socket
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from costguard_agent import device, export as export_mod, sync as sync_mod


class SyncPrepTest(unittest.TestCase):
    # ---- fixtures -------------------------------------------------------
    @classmethod
    def setUpClass(cls):
        cls.export_payload = export_mod.build_export_payload()
        cls.device_id = device.get_or_create()
        cls.dto = sync_mod.to_ingest_dto(cls.export_payload, cls.device_id,
                                         created_at="2026-09-04T00:00:00+00:00")

    # ---- S1 schema validation ------------------------------------------
    def test_s1_export_schema_valid(self):
        p = self.export_payload
        for key in ("schema_version", "exported_at", "granularity",
                    "days", "usage"):
            self.assertIn(key, p)
        self.assertEqual(p["schema_version"], 1)
        for day, obj in p["usage"].items():
            # day allowlist: exactly the permitted keys
            self.assertEqual(set(obj), set(export_mod.ALLOWED_DAY_KEYS),
                             f"{day}: {set(obj)}")
            self.assertIsInstance(obj["tokens"], int)
            self.assertIsInstance(obj["events"], int)
            self.assertEqual(set(obj["cost"]),
                             {"estimated", "unknown_passthrough"})
            for model, m in obj["models"].items():
                self.assertIsInstance(m["tokens"], int)
                for provider, pv in m["providers"].items():
                    self.assertIsInstance(pv["token_count"], int)
                    self.assertGreaterEqual(pv["token_count"], 0)
                    self.assertTrue(all(isinstance(v, int) and v >= 0
                                        for v in pv["sources"].values()))
        # token conservation: provider tokens sum to model tokens
        for obj in p["usage"].values():
            for m in obj["models"].values():
                self.assertEqual(sum(pv["token_count"]
                                     for pv in m["providers"].values()),
                                 m["tokens"])

    def test_s1_dto_schema_valid(self):
        dto = self.dto
        self.assertEqual(set(dto), {"schema_version", "device", "sync",
                                    "records"})
        self.assertEqual(dto["schema_version"], 1)
        self.assertEqual(set(dto["device"]), {"device_id", "agent_version"})
        self.assertEqual(set(dto["sync"]), {"created_at", "mode",
                                            "dry_run", "enabled"})
        self.assertTrue(sync_mod.RECORD_FIELDS)
        for rec in dto["records"]:
            self.assertEqual(set(rec), set(sync_mod.RECORD_FIELDS))
            self.assertRegex(rec["date"], r"^\d{4}-\d{2}-\d{2}$")
            self.assertIsInstance(rec["token_count"], int)
            self.assertIn(rec["cost_status"], ("estimated", "unknown"))
            self.assertIsInstance(rec["estimated_cost"], (int, float))
        # conservation: record tokens per day sum to export day tokens
        by_day: dict[str, int] = {}
        for rec in dto["records"]:
            by_day[rec["date"]] = by_day.get(rec["date"], 0) + rec["token_count"]
        for day, obj in self.export_payload["usage"].items():
            self.assertEqual(by_day.get(day, 0), obj["tokens"],
                             f"{day}: DTO tokens != export tokens")

    def test_s1_dto_writes_and_matches(self):
        with tempfile.TemporaryDirectory() as td:
            out = sync_mod.write_dto(self.dto, path=str(Path(td) / "dto.json"))
            self.assertEqual(json.loads(Path(out).read_text()), self.dto)
            self.assertEqual(oct(out.stat().st_mode & 0o777), "0o600")

    # ---- S2 privacy ------------------------------------------------------
    def test_s2_no_privacy_fields(self):
        blob = json.dumps(self.export_payload).lower()
        for word in ("prompt", "response", "content", "message", "secret",
                     "api_key", "token_key", "filename", "filepath",
                     "file_path", "session_ref", "first_user_message",
                     "preview", "origin_json", "system_prompt"):
            self.assertNotIn(f'"{word}"', blob, f"export leaks {word}")
        blob2 = json.dumps(self.dto).lower()
        for word in ("prompt", "response", "content", "message", "secret",
                     "api_key", "filename", "path", "session_ref", "cwd",
                     "title"):
            self.assertNotIn(f'"{word}"', blob2, f"DTO leaks {word}")

    def test_s2_forbidden_key_gate_raises(self):
        bad = {"records": [{"prompt": "hello"}]}
        with self.assertRaises(PermissionError):
            sync_mod.assert_no_forbidden_payload(bad)
        bad2 = {"usage": {"2026-01-01": {"path": "/home/user/secret"}}}
        with self.assertRaises(PermissionError):
            export_mod.assert_no_forbidden_payload(bad2)

    def test_s2_records_allowlist_exhaustive(self):
        for rec in self.dto["records"]:
            self.assertTrue(set(rec) <= set(sync_mod.RECORD_FIELDS))
            for field in sync_mod.RECORD_FIELDS:
                self.assertIn(field, rec)

    # ---- S3 sync default OFF, no network --------------------------------
    def test_s3_sync_default_off(self):
        st = sync_mod.status()
        self.assertFalse(st["enabled"])
        self.assertIsNone(st["transport"])
        self.assertFalse(sync_mod.SYNC_DEFAULT_ENABLED)
        # the DTO itself carries enabled=false
        self.assertFalse(self.dto["sync"]["enabled"])
        self.assertTrue(self.dto["sync"]["dry_run"])

    def test_s3_no_send_api_exists(self):
        self.assertFalse(hasattr(sync_mod, "send"))
        self.assertFalse(hasattr(sync_mod, "upload"))
        self.assertFalse(hasattr(sync_mod, "post"))
        src = Path(sync_mod.__file__).read_text()
        for banned in ("requests.", "urllib.request", "http.client",
                       "socket.socket", "urlopen"):
            self.assertNotIn(banned, src, f"sync module references {banned}")

    def test_s3_sync_blocked_without_network(self):
        """DTO build must succeed with networking completely disabled —
        proving no hidden network dependency."""
        real_socket = socket.socket

        class Blocked(real_socket):
            def __init__(self, *a, **k):
                raise OSError("network disabled by test")

        socket.socket = Blocked
        try:
            payload = export_mod.build_export_payload()
            dto = sync_mod.to_ingest_dto(payload, self.device_id)
            self.assertTrue(dto["records"])
        finally:
            socket.socket = real_socket

    # ---- S4 device identity ---------------------------------------------
    def test_s4_device_id_stable_and_valid(self):
        did1 = device.get_or_create()
        did2 = device.get_or_create()
        self.assertEqual(did1, did2)               # stable across calls
        self.assertTrue(device.is_valid(did1))     # cg-<32 hex>
        self.assertTrue(did1.startswith("cg-"))
        self.assertEqual(len(did1), 35)

    def test_s4_device_id_tempfile_isolated(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "device_id"
            a = device.get_or_create(path=f)
            b = device.get_or_create(path=f)
            self.assertEqual(a, b)
            self.assertTrue(device.is_valid(a))
            self.assertEqual(oct(f.stat().st_mode & 0o777), "0o600")
            # corrupt file -> replaced with a fresh valid id, never trusted
            f.write_text("not-an-id")
            c = device.get_or_create(path=f)
            self.assertTrue(device.is_valid(c))
            self.assertNotEqual(c, "not-an-id")

    def test_s4_device_id_not_pii_derived(self):
        a = device.new_device_id()
        b = device.new_device_id()
        self.assertNotEqual(a, b)   # pure randomness, two calls differ


if __name__ == "__main__":
    unittest.main(verbosity=2)
