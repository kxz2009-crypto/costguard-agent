"""P1A-09 public pricing tests (optional, DEFAULT OFF slice).

Covers: flag semantics (F1), OFF no-op (F2), known-model Decimal text cost
(P1), unknown model (P2), cache read/write classes (P3), reasoning class
(P4), missing price with tokens>0 (P5), duplicate never mutates money
(I1), client spoof still 422 at the API edge (S1), no float/REAL/DOUBLE in
the pricing module (N1), version written (V1), and no P1B capability
keywords in code (B1). All pricing behaviour uses a temp copy of the
public table; no host data, no network.
"""

from __future__ import annotations

import ast
import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from costguard_split import db as split_db
from costguard_split.api.context import ServerContext, TenantViolation
from costguard_split.ingest.service import (
    IngestConflict,
    ingest_usage_event,
)
from costguard_split.ingest import pricing_public
from costguard_split.ingest.pricing_public import (
    estimate_cost,
    public_pricing_enabled,
)
from costguard_split.schemas.usage import UsageEventClaim

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_TABLE = (
    REPO_ROOT / "costguard_split" / "data" / "public_pricing.json")

UID_A = "cgdev_018f0c9a-1605-4bec-8000-17b71faba7e1"
T1 = "2026-09-10T00:00:00+00:00"
T2 = "2026-09-20T00:00:00+00:00"

# A deterministic fixture table: prices chosen so every arithmetic path is
# hand-checkable with Decimal.
FIXTURE_TABLE = {
    "version": "public-test-1",
    "models": [
        {
            "provider": "claude",
            "model": "full-model",
            "input_per_mtok": "3.0000",
            "output_per_mtok": "15.0000",
            "cache_read_per_mtok": "0.3000",
            "cache_write_per_mtok": "3.7500",
            "reasoning_per_mtok": "0.5000",
        },
        {
            # no cache_write / reasoning prices: any tokens there -> NULL
            "provider": "claude",
            "model": "partial-model",
            "input_per_mtok": "1.0000",
            "output_per_mtok": "2.0000",
            "cache_read_per_mtok": "0.1000",
        },
    ],
}


def claim(**overrides) -> UsageEventClaim:
    values = {
        "device_uid": UID_A,
        "provider": "claude",
        "source_event_id": "evt-1",
        "model": "full-model",
        "started_at": T1,
        "ended_at": T2,
        "session_ref": "session-a",
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "cache_write_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "request_count": 1,
        "collector_version": "test-collector",
        "source_type": "connector",
    }
    values.update(overrides)
    return UsageEventClaim(**values)


class _FlagTestCase(unittest.TestCase):
    """Base: temp table copy + flag scrubbed + isolated DB."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.table_path = Path(self._tmp.name) / "table.json"
        self.table_path.write_text(
            json.dumps(FIXTURE_TABLE), encoding="utf-8")
        self._old_flag = os.environ.pop(pricing_public.FLAG_ENV, None)
        self.db_path = Path(self._tmp.name) / "split.db"
        self.db = split_db.connect(path=self.db_path)
        self.db.executemany(
            "INSERT INTO organizations (id,name,status,created_at,"
            "updated_at) VALUES (?,?,'active','t','t')",
            (("org-a", "A"),))
        self.db.executemany(
            "INSERT INTO devices (id,organization_id,device_uid,"
            "display_name,hostname_hash,username_hash,os,arch,"
            "first_seen_at,last_seen_at,status,identity_confidence,"
            "collector_version,created_at,updated_at) "
            "VALUES ('dev-a','org-a',?,'d','hk1:a','hk1:b','Linux',"
            "'x86_64','t','t','active',0,'','t','t')", ((UID_A,),))
        self.db.commit()
        self.ctx = ServerContext("org-a", "pricing-test")

    def tearDown(self):
        self.db.close()
        self._tmp.cleanup()
        if self._old_flag is not None:
            os.environ[pricing_public.FLAG_ENV] = self._old_flag
        else:
            os.environ.pop(pricing_public.FLAG_ENV, None)

    def _estimate(self, claim_value):
        return estimate_cost(claim_value, table_path=self.table_path)

    def _ingest(self, claim_value):
        # route estimate through the real service but with the temp table
        with patch.object(
                pricing_public, "_TABLE_PATH", self.table_path):
            return ingest_usage_event(self.db, context=self.ctx,
                                      claim=claim_value)

    def _money(self, event_id):
        return self.db.execute(
            "SELECT pricing_version, api_equivalent_cost_usd "
            "FROM usage_events WHERE id = ?", (event_id,)).fetchone()


class FlagTests(_FlagTestCase):
    def test_f1_default_off_and_strict_optin(self):
        for env_value, expected in (
                (None, False), ("", False), ("0", False), ("off", False),
                ("yes", False), ("True", False), ("true ", False),
                ("1", True), ("true", True), ("TRUE", True)):
            os.environ.pop(pricing_public.FLAG_ENV, None)
            if env_value is not None:
                os.environ[pricing_public.FLAG_ENV] = env_value
            self.assertIs(public_pricing_enabled(), expected,
                          msg=f"flag={env_value!r}")


class EstimateTests(_FlagTestCase):
    def setUp(self):
        super().setUp()
        # P1-P5 exercise the ENABLED path; F1/F2 own the OFF semantics.
        os.environ[pricing_public.FLAG_ENV] = "1"

    def test_f2_off_means_always_null(self):
        os.environ.pop(pricing_public.FLAG_ENV, None)
        self.assertEqual(self._estimate(claim()), (None, None))

    def test_p1_known_model_decimal_text(self):
        # input 1_000_000*3 + output 100_000*15 = 3 + 1.5 = 4.5 -> 4.5000
        version, cost = self._estimate(claim(
            input_tokens=1_000_000, output_tokens=100_000))
        self.assertEqual((version, cost),
                         ("public-test-1", "4.5000"))
        self.assertIsInstance(cost, str)

    def test_p1_rounding_half_up_at_4dp(self):
        # 1 token at 3.0/mtok = 0.000003 -> 0.0000; boundary checks
        version, cost = self._estimate(claim(input_tokens=2))
        self.assertEqual(cost, "0.0000")
        # 833_333 * 3 / 1e6 = 2.499999 -> 2.5000 (half-up on the 4th dp)
        version, cost = self._estimate(claim(
            input_tokens=833_333, output_tokens=2))
        self.assertEqual(cost, "2.5000")

    def test_p2_unknown_model_is_null(self):
        self.assertEqual(
            self._estimate(claim(model="claude-opus-9-nonexistent")),
            (None, None))

    def test_p2_unknown_provider_is_null(self):
        self.assertEqual(
            self._estimate(claim(provider="codex", model="full-model")),
            (None, None))

    def test_p3_cache_read_and_write_classes(self):
        # read: 2_000_000*0.3 = 600k ; write: 1_000_000*3.75 = 3.75M
        # total 4_350_000 / 1e6 = 4.35
        version, cost = self._estimate(claim(
            cached_input_tokens=2_000_000, cache_write_tokens=1_000_000))
        self.assertEqual(cost, "4.3500")

    def test_p4_reasoning_class(self):
        version, cost = self._estimate(claim(
            reasoning_tokens=400_000))
        self.assertEqual(cost, "0.2000")

    def test_p5_missing_price_with_positive_tokens_is_null(self):
        # cache_write tokens > 0 but partial-model has no write price
        self.assertEqual(
            self._estimate(claim(
                model="partial-model", cache_write_tokens=5)),
            (None, None))
        # reasoning tokens > 0 but no reasoning price
        self.assertEqual(
            self._estimate(claim(
                model="partial-model", reasoning_tokens=5)),
            (None, None))
        # zero tokens with missing price stays priced on present classes
        version, cost = self._estimate(claim(
            model="partial-model", input_tokens=1_000_000,
            cache_write_tokens=0, reasoning_tokens=0))
        self.assertEqual(cost, "1.0000")

    def test_corrupt_table_fails_open_to_null(self):
        broken = Path(self._tmp.name) / "broken.json"
        broken.write_text(json.dumps({
            "version": "public-bad",
            "models": [{"provider": "claude", "model": "full-model",
                        "input_per_mtok": 3.0}]}), encoding="utf-8")
        with patch.object(pricing_public, "public_pricing_enabled",
                          return_value=True):
            self.assertEqual(
                estimate_cost(claim(input_tokens=5), table_path=broken),
                (None, None))


class IngestIntegrationTests(_FlagTestCase):
    def test_f2_off_ingest_keeps_money_null(self):
        result = self._ingest(claim())
        self.assertEqual(result.status, "created")
        self.assertEqual(self._money(result.event.id), (None, None))

    def test_p1_v1_on_ingest_writes_decimal_text_and_version(self):
        with patch.object(
                pricing_public, "_TABLE_PATH", self.table_path), patch.object(
                pricing_public, "public_pricing_enabled",
                return_value=True):
            result = ingest_usage_event(self.db, context=self.ctx,
                                        claim=claim(
                                            input_tokens=1_000_000,
                                            output_tokens=100_000))
        self.assertEqual(result.status, "created")
        self.assertEqual(self._money(result.event.id),
                         ("public-test-1", "4.5000"))

    def test_i1_duplicate_never_mutates_money(self):
        with patch.object(
                pricing_public, "_TABLE_PATH", self.table_path), patch.object(
                pricing_public, "public_pricing_enabled",
                return_value=True):
            first = ingest_usage_event(self.db, context=self.ctx,
                                       claim=claim(input_tokens=1_000_000))
            before = self._money(first.event.id)
            self.assertEqual(before, ("public-test-1", "3.0000"))
            # flag turned OFF for the replay: duplicate must not change it
            replay = ingest_usage_event(self.db, context=self.ctx,
                                        claim=claim(input_tokens=1_000_000))
        self.assertEqual(replay.status, "duplicate")
        self.assertEqual(self._money(replay.event.id), before)

    def test_audit_still_allowlisted_with_pricing_on(self):
        with patch.object(
                pricing_public, "_TABLE_PATH", self.table_path), patch.object(
                pricing_public, "public_pricing_enabled",
                return_value=True):
            result = ingest_usage_event(self.db, context=self.ctx,
                                        claim=claim(input_tokens=10))
        blob = " ".join(str(v) for row in self.db.execute(
            "SELECT before_json, after_json FROM audit_events WHERE "
            "event_type LIKE 'usage.%'").fetchall() for v in row)
        self.assertNotIn("cost", blob.lower())
        self.assertNotIn("api_equivalent", blob.lower())


class SourceBoundaryTests(unittest.TestCase):
    def test_n1_no_float_real_double_in_pricing_module(self):
        source = pricing_public.__file__
        tree = ast.parse(Path(source).read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
        self.assertTrue({"Decimal", "ROUND_HALF_UP"} <= imported)
        self.assertNotIn("float", imported)
        names = {n.id for n in ast.walk(tree)
                 if isinstance(n, ast.Name)}
        self.assertNotIn("float", names)
        self.assertNotIn("float(", Path(source).read_text())
        # DDL/text guard mirrors the repo-wide money policy
        text = Path(source).read_text(encoding="utf-8")
        for forbidden in ("REAL", "DOUBLE"):
            self.assertNotIn(forbidden, text)

    def test_n1_public_table_uses_decimal_strings(self):
        raw = json.loads(REAL_TABLE.read_text(encoding="utf-8"),
                         parse_float=_reject)
        self.assertIsInstance(raw["version"], str)
        self.assertTrue(raw["version"].startswith("public-"))
        for row in raw["models"]:
            for key, value in row.items():
                if key.endswith("_per_mtok"):
                    self.assertIsInstance(value, str, msg=(row, key))

    def test_b1_no_p1b_capability_keywords_in_code(self):
        tree = ast.parse(
            (REPO_ROOT / "costguard_split" / "ingest" /
             "pricing_public.py").read_text(encoding="utf-8"))
        identifiers = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
                identifiers.add(node.name.lower())
            elif isinstance(node, ast.Name):
                identifiers.add(node.id.lower())
            elif isinstance(node, ast.Attribute):
                identifiers.add(node.attr.lower())
        for token in ("attribution", "lineage", "confidence", "quota",
                      "recommendation", "optimization", "billing",
                      "settlement", "allocation", "revenue"):
            hits = [name for name in identifiers if token in name]
            self.assertEqual(hits, [], msg=token)

    def test_s1_client_spoof_money_still_rejected_at_schema(self):
        from pydantic import ValidationError
        base = claim().model_dump()
        for field in ("pricing_version", "api_equivalent_cost_usd"):
            with self.assertRaises(ValidationError, msg=field):
                UsageEventClaim(**{**base, field: "0.0001"})


def _reject(text):
    raise AssertionError(f"table contains float literal: {text}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
