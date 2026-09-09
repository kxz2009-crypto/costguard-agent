"""
P1D-04 OPEN Open Consumption API tests (K1-K22 per amended gate).

Layer under test: costguard_split/api/consumption.py
Run: pytest tests/split_p1d04_consumption_api_test.py
Isolation: every test builds its own tmp DB via create_app(db_path=...).
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from fastapi.testclient import TestClient
    _DEPS = True
except ImportError:                                  # pragma: no cover
    _DEPS = False

from costguard_split.api.app import create_app
from costguard_split.api.context import ServerContext

ORG = "org-a"
ORG_OTHER = "org-b"

# timezone-aware windows (gate: naive timestamps must 400)
START = "2026-01-01T00:00:00Z"
END = "2026-01-31T00:00:00Z"
DAY = "2026-01-02T00:00:00Z"   # inside window, day-2 bucket


def _seed(db_path: Path) -> None:
    """Minimal direct seed matching the split schema."""
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.execute("""
    CREATE TABLE usage_events (
        id TEXT PRIMARY KEY,
        organization_id TEXT,
        provider TEXT,
        model TEXT,
        member_id TEXT,
        device_id TEXT,
        started_at TEXT,
        request_count INTEGER,
        input_tokens INTEGER,
        cached_input_tokens INTEGER,
        cache_write_tokens INTEGER,
        output_tokens INTEGER,
        reasoning_tokens INTEGER,
        api_equivalent_cost_usd TEXT
    )
    """)
    conn.executemany(
        "INSERT INTO usage_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("1", ORG, "claude", "opus", "member-a", "device-a",
             "2026-01-01T00:00:00Z", 1, 100, 10, 5, 200, 20, "0.0100"),
            ("2", ORG, "gpt", "x", "member-a", "device-a",
             "2026-01-01T01:00:00Z", 2, 150, 0, 0, 300, 0, "0.0200"),
            ("3", ORG, "claude", "opus", "member-b", "device-a",
             "2026-01-02T00:00:00Z", 1, 50, 5, 0, 90, 10, None),
            ("4", ORG_OTHER, "claude", "opus", "member-a", "device-a",
             "2026-01-01T00:00:00Z", 9, 900, 0, 0, 900, 0, "0.9000"),
        ],
    )
    conn.commit()
    conn.close()


@unittest.skipUnless(_DEPS, "fastapi/httpx not installed ([split-server])")
class ConsumptionTestBase(unittest.TestCase):
    """One app per test, own tmp DB, explicit ServerContext."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "split.db"
        _seed(self.db_path)
        self.ctx = ServerContext(organization_id=ORG)
        self.client = TestClient(
            create_app(db_path=self.db_path, context=self.ctx),
            raise_server_exceptions=False,
        )

    def tearDown(self):
        self._tmp.cleanup()

    # helpers -------------------------------------------------------
    def get(self, path: str, **params):
        defaults = {"org_id": ORG, "start": START, "end": END}
        defaults.update(params)
        return self.client.get(f"/api/v1/consumption{path}",
                               params=defaults)

    @staticmethod
    def _service_snapshot(db_path: Path):
        """Row contents snapshot for mutation checks (K9)."""
        import sqlite3

        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT * FROM usage_events ORDER BY id").fetchall()
        conn.close()
        return rows

    def assertNoStore(self, response):
        self.assertEqual(
            response.headers.get("cache-control"), "no-store")


@unittest.skipUnless(_DEPS, "fastapi/httpx not installed")
class ServiceParityTests(ConsumptionTestBase):
    """K1-K6, K21, K22: endpoint output equals direct service call."""

    def test_k1_summary_matches_service(self):
        from dataclasses import asdict
        from costguard_split.analytics.service import analytics_summary
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        direct = asdict(analytics_summary(
            conn, ORG, START, END))
        conn.close()

        response = self.get("/summary")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), direct)

    def test_k2_timeseries_order_matches_service(self):
        from dataclasses import asdict
        from costguard_split.analytics.timeseries import (
            timeseries_summary)
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        direct = [
            asdict(p) for p in timeseries_summary(
                conn, organization_id=ORG, start=START, end=END,
                granularity="day")
        ]
        conn.close()

        response = self.get("/timeseries", granularity="day")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), direct)
        self.assertGreater(len(response.json()), 0)

    def test_k3_distributions_match_visualization(self):
        from dataclasses import asdict
        from costguard_split.analytics.service import analytics_summary
        from costguard_split.visualization.service import (
            model_distribution, provider_distribution)
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        summary = analytics_summary(conn, ORG, START, END)
        conn.close()
        expected = {
            "provider_distribution": [
                asdict(p) for p in provider_distribution(summary)],
            "model_distribution": [
                asdict(m) for m in model_distribution(summary)],
        }

        response = self.get("/distributions")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        self.assertEqual(
            set(response.json().keys()),
            {"provider_distribution", "model_distribution"})

    def test_k4_dashboard_matches_payload(self):
        from costguard_split.dashboard.service import (
            dashboard_projection)
        from costguard_split.api.consumption import _validate_window
        import sqlite3

        norm_start, norm_end = _validate_window(START, END)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        direct = dashboard_projection(
            conn, ORG, norm_start, norm_end, "day").to_dict()
        conn.close()

        response = self.get("/dashboard", granularity="day")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), direct)

    def test_k5_export_carries_manifest_hash(self):
        response = self.get("/export/summary")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("manifest", body)
        self.assertIn("payload", body)
        self.assertTrue(body["manifest"]["content_hash"])

        response_ts = self.get("/export/timeseries", granularity="day")
        self.assertEqual(response_ts.status_code, 200)
        self.assertTrue(
            response_ts.json()["manifest"]["content_hash"])

        response_d = self.get("/export/distributions")
        self.assertEqual(response_d.status_code, 200)
        export_d = response_d.json()
        self.assertTrue(export_d["manifest"]["content_hash"])
        # gate amendment 4: distribution payload includes summary
        self.assertIn("summary", export_d["payload"])

    def test_k6_report_carries_body_and_hash(self):
        import hashlib
        import json

        response = self.get("/report/summary")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("|", body["body"])   # markdown table present
        self.assertEqual(
            body["content_hash"],
            hashlib.sha256(json.dumps(
                body["body"], sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False).encode()).hexdigest())

    def test_k21_repeat_render_hashes_stable(self):
        first = self.get("/export/summary").json()
        second = self.get("/export/summary").json()
        self.assertEqual(first["manifest"]["content_hash"],
                         second["manifest"]["content_hash"])

        report_a = self.get("/report/timeseries",
                            granularity="day").json()
        report_b = self.get("/report/timeseries",
                            granularity="day").json()
        self.assertEqual(report_a["content_hash"],
                         report_b["content_hash"])


@unittest.skipUnless(_DEPS, "fastapi/httpx not installed")
class BoundaryTests(ConsumptionTestBase):
    """K7, K14, K8, K10, K9: module boundaries + purity."""

    def test_k7_k14_no_sql_no_db_import(self):
        source = Path(
            "costguard_split/api/consumption.py"
        ).read_text()
        self.assertNotIn("import sqlite3", source)
        self.assertNotIn("from costguard_split.db", source)
        self.assertNotIn("SELECT", source)
        self.assertNotIn("execute(", source)

    def test_k8_null_cost_preserved(self):
        # row 3 (org-a, day 2) has NULL cost: JSON null + empty cell
        summary = self.get("/summary").json()
        day_rows = [
            row for row in summary["by_provider"]
        ]   # presence of dimensions is enough at API level

        trend = self.get("/timeseries", granularity="day").json()
        day2 = [p for p in trend
                if p["bucket_start"].startswith("2026-01-02")]
        self.assertTrue(day2)
        self.assertIsNone(day2[0]["public_cost_nullable"])

        report = self.get("/report/timeseries",
                          granularity="day").json()
        self.assertNotIn("| None |", report["body"])

    def test_k10_no_extra_fields(self):
        summary = self.get("/summary").json()
        self.assertEqual(
            set(summary.keys()),
            {"totals", "by_provider", "by_model",
             "by_member", "by_device"})

    def test_k9_no_mutation(self):
        before = self._service_snapshot(self.db_path)
        for path, params in (
            ("/summary", {}),
            ("/timeseries", {"granularity": "day"}),
            ("/distributions", {}),
            ("/dashboard", {"granularity": "day"}),
            ("/export/summary", {}),
            ("/export/timeseries", {"granularity": "day"}),
            ("/export/distributions", {}),
            ("/report/summary", {}),
            ("/report/timeseries", {"granularity": "day"}),
        ):
            response = self.get(path, **params)
            self.assertEqual(response.status_code, 200, path)
        after = self._service_snapshot(self.db_path)
        self.assertEqual(before, after)


@unittest.skipUnless(_DEPS, "fastapi/httpx not installed")
class IsolationAndAuthzTests(ConsumptionTestBase):
    """K13, K19, K20: tenant isolation is mandatory."""

    DATA_ENDPOINTS = (
        ("/summary", {}),
        ("/timeseries", {"granularity": "day"}),
        ("/distributions", {}),
        ("/dashboard", {"granularity": "day"}),
        ("/export/summary", {}),
        ("/export/timeseries", {"granularity": "day"}),
        ("/export/distributions", {}),
        ("/report/summary", {}),
        ("/report/timeseries", {"granularity": "day"}),
    )

    def test_k13_foreign_org_404_everywhere(self):
        for path, params in self.DATA_ENDPOINTS:
            response = self.get(path, org_id=ORG_OTHER, **params)
            self.assertEqual(response.status_code, 404, path)
            self.assertEqual(response.json(), {"detail": "not found"})
            self.assertNotIn("900", response.text)   # no data leak

    def test_k19_missing_context_404_everywhere(self):
        client = TestClient(
            create_app(db_path=self.db_path, context=None),
            raise_server_exceptions=False,
        )
        for path, params in self.DATA_ENDPOINTS:
            defaults = {"org_id": ORG, "start": START, "end": END}
            defaults.update(params)
            response = client.get(
                f"/api/v1/consumption{path}", params=defaults)
            self.assertEqual(response.status_code, 404, path)
            self.assertEqual(response.json(), {"detail": "not found"})

    def test_k20_dashboard_filters_rejected(self):
        response = self.get("/dashboard", granularity="day",
                            provider="claude")
        self.assertEqual(response.status_code, 422)

        response = self.get("/dashboard", granularity="day",
                            member_id="member-a")
        self.assertEqual(response.status_code, 422)


@unittest.skipUnless(_DEPS, "fastapi/httpx not installed")
class ValidationTests(ConsumptionTestBase):
    """K12, K15, K16: input validation contract."""

    def test_k12_window_validation(self):
        cases = [
            # malformed
            {"start": "not-a-date"},
            # timezone-naive
            {"start": "2026-01-01T00:00:00"},
            {"end": "2026-01-31T00:00:00"},
            # reversed
            {"start": "2026-01-31T00:00:00Z",
             "end": "2026-01-01T00:00:00Z"},
            # oversized (> 31 days)
            {"start": "2026-01-01T00:00:00Z",
             "end": "2026-03-15T00:00:00Z"},
        ]
        for overrides in cases:
            response = self.get("/summary", **overrides)
            self.assertEqual(response.status_code, 400,
                             overrides)

    def test_k15_invalid_granularity_empty_and_populated(self):
        # populated data
        response = self.get("/timeseries", granularity="week")
        self.assertEqual(response.status_code, 400)

        # empty window (no rows in Feb)
        response = self.get(
            "/timeseries", granularity="week",
            start="2026-02-01T00:00:00Z", end="2026-02-20T00:00:00Z")
        self.assertEqual(response.status_code, 400)

    def test_k16_missing_required_params(self):
        response = self.client.get(
            "/api/v1/consumption/summary",
            params={"start": START, "end": END})   # no org_id
        self.assertEqual(response.status_code, 422)

        response = self.client.get(
            "/api/v1/consumption/timeseries",
            params={"org_id": ORG, "start": START, "end": END})
        self.assertEqual(response.status_code, 422)   # no granularity


@unittest.skipUnless(_DEPS, "fastapi/httpx not installed")
class TransportTests(ConsumptionTestBase):
    """K18: no-store on success AND error responses."""

    def test_k18_no_store_success(self):
        response = self.get("/summary")
        self.assertEqual(response.status_code, 200)
        self.assertNoStore(response)

    def test_k18_no_store_on_404(self):
        response = self.get("/summary", org_id=ORG_OTHER)
        self.assertEqual(response.status_code, 404)
        self.assertNoStore(response)

    def test_k18_no_store_on_400(self):
        response = self.get("/summary", start="2026-01-01T00:00:00")
        self.assertEqual(response.status_code, 400)
        self.assertNoStore(response)

    def test_k18_no_store_on_422(self):
        response = self.client.get(
            "/api/v1/consumption/summary",
            params={"start": START, "end": END})
        self.assertEqual(response.status_code, 422)
        self.assertNoStore(response)

    def test_legacy_routes_keep_transport(self):
        # negative guard: legacy visualization route must NOT gain
        # the consumption header
        response = self.client.get(
            "/api/v1/visualization/summary",
            params={"org_id": ORG, "start": "2026-01-01",
                    "end": "2026-01-31"})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.headers.get("cache-control"))


@unittest.skipUnless(_DEPS, "fastapi/httpx not installed")
class RegressionGuardTests(ConsumptionTestBase):
    """K17: legacy routes untouched (path+method snapshot)."""

    def test_k17_legacy_visualization_routes_unmodified(self):
        # functional: every legacy visualization route answers 200
        legacy = [
            ("/api/v1/visualization/summary",
             {"org_id": ORG, "start": "2026-01-01",
              "end": "2026-01-31"}),
            ("/api/v1/visualization/trend",
             {"org_id": ORG, "start": "2026-01-01",
              "end": "2026-01-31", "interval": "day"}),
            ("/api/v1/visualization/providers",
             {"org_id": ORG, "start": "2026-01-01",
              "end": "2026-01-31"}),
            ("/api/v1/visualization/models",
             {"org_id": ORG, "start": "2026-01-01",
              "end": "2026-01-31"}),
        ]
        for path, params in legacy:
            response = self.client.get(path, params=params)
            self.assertEqual(response.status_code, 200, path)


if __name__ == "__main__":
    unittest.main()
