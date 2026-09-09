"""
P1D-02 OPEN Dashboard Read Projection tests.

Covers:
D-1 payload totals match visualization summary
D-2 payload distributions match visualization output
D-3 payload trend matches timeseries output
D-4 determinism: identical inputs -> equal payloads
D-5 meta completeness (schema_version, baseline, window, granularity, filters)
D-6 org isolation
D-7 projection does not mutate db
D-8 module imports no db / sqlite3
D-9 unsupported granularity surfaces timeseries error
"""

from __future__ import annotations

import sqlite3
import unittest
from dataclasses import asdict

from costguard_split.analytics.service import analytics_summary
from costguard_split.analytics.timeseries import timeseries_summary
from costguard_split.dashboard import dashboard_projection
from costguard_split.visualization.service import (
    model_distribution,
    provider_distribution,
    visualization_summary,
)


class DashboardTestBase(unittest.TestCase):

    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row

        self.db.execute("""
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

        self.db.executemany(
            """
            INSERT INTO usage_events VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("1", "org-a", "claude", "opus", "member-a", "device-a",
                 "2026-01-01T00:00:00Z", 1, 100, 10, 5, 200, 20, "0.0100"),
                ("2", "org-a", "gpt", "x", "member-a", "device-a",
                 "2026-01-01T01:00:00Z", 2, 150, 0, 0, 300, 0, "0.0200"),
                ("3", "org-a", "claude", "opus", "member-b", "device-a",
                 "2026-01-02T00:00:00Z", 1, 50, 5, 0, 90, 10, "0.0050"),
                ("4", "org-b", "claude", "opus", "member-a", "device-a",
                 "2026-01-01T00:00:00Z", 9, 900, 0, 0, 900, 0, "0.9000"),
            ],
        )
        self.db.commit()

    def _projection(self, org="org-a", **kwargs):
        defaults = dict(
            start="2026-01-01",
            end="2026-01-31",
            granularity="day",
        )
        defaults.update(kwargs)
        return dashboard_projection(self.db, org, **defaults)


class DashboardPayloadTests(DashboardTestBase):

    def test_payload_totals_match_visualization_summary(self):
        """D-1 totals section equals visualization_summary output."""
        direct = analytics_summary(
            self.db, "org-a", "2026-01-01", "2026-01-31")
        expected = visualization_summary(direct)

        payload = self._projection()

        self.assertEqual(payload.totals, asdict(expected))
        self.assertEqual(payload.totals["events"], expected.events)
        self.assertEqual(payload.totals["tokens"], expected.tokens)

    def test_payload_distributions_match_visualization_output(self):
        """D-2 distribution sections equal visualization layer output."""
        direct = analytics_summary(
            self.db, "org-a", "2026-01-01", "2026-01-31")
        expected_providers = [
            asdict(point) for point in provider_distribution(direct)]
        expected_models = [
            asdict(point) for point in model_distribution(direct)]

        payload = self._projection()

        self.assertEqual(
            payload.provider_distribution, expected_providers)
        self.assertEqual(payload.model_distribution, expected_models)

    def test_payload_trend_matches_timeseries_output(self):
        """D-3 trend section equals timeseries layer output in order."""
        direct = timeseries_summary(
            self.db, organization_id="org-a",
            start="2026-01-01", end="2026-01-31", granularity="day")

        payload = self._projection()

        self.assertEqual(len(payload.trend), len(direct))
        for exported, point in zip(payload.trend, direct):
            self.assertEqual(exported, asdict(point))


class DashboardDeterminismTests(DashboardTestBase):

    def test_payload_determinism_equal_payloads(self):
        """D-4 identical inputs produce equal payload dicts."""
        first = self._projection().to_dict()
        second = self._projection().to_dict()
        self.assertEqual(first, second)


class DashboardMetaTests(DashboardTestBase):

    def test_meta_completeness(self):
        """D-5 meta carries schema_version, baseline, window,
        granularity and filter echo."""
        payload = self._projection(
            provider="claude",
            model="opus",
            member_id="member-a",
            device_id="device-a",
        )
        as_dict = payload.to_dict()

        self.assertEqual(as_dict["meta"]["schema_version"], "1")
        self.assertEqual(as_dict["meta"]["baseline"], "v0.6.0-p1d01")
        self.assertEqual(
            as_dict["meta"]["window"],
            {"start": "2026-01-01", "end": "2026-01-31"})
        self.assertEqual(as_dict["meta"]["granularity"], "day")
        self.assertEqual(
            as_dict["meta"]["filters"],
            {
                "provider": "claude",
                "model": "opus",
                "member_id": "member-a",
                "device_id": "device-a",
            })


class DashboardBoundaryTests(DashboardTestBase):

    def test_org_isolation(self):
        """D-6 events from other organizations never appear."""
        payload = self._projection(org="org-a")

        all_keys = [point["key"]
                    for point in payload.provider_distribution]
        self.assertNotIn(None, all_keys)

        # org-b has 9 requests in its own rows; none may leak in.
        self.assertLess(payload.totals["events"], 4)

        payload_b = self._projection(org="org-b")
        self.assertEqual(payload_b.totals["events"], 1)

    def test_projection_does_not_mutate_db(self):
        """D-7 projection never writes: row count stable."""
        before = self.db.execute(
            "SELECT COUNT(*) FROM usage_events").fetchone()[0]

        self._projection()
        self._projection(granularity="hour")

        after = self.db.execute(
            "SELECT COUNT(*) FROM usage_events").fetchone()[0]
        self.assertEqual(before, after)
        self.assertFalse(self.db.in_transaction)

    def test_module_does_not_import_db_or_sqlite3(self):
        """D-8 dashboard modules import no db module, no sqlite3."""
        import costguard_split.dashboard.service as service
        import sys

        for module_file in (service.__file__,):
            source = open(module_file, encoding="utf-8").read()
            self.assertNotIn("import sqlite3", source)
            self.assertNotIn("from costguard_split.db", source)

        loaded = sys.modules.get("costguard_split.dashboard.service")
        self.assertIsNotNone(loaded)
        self.assertFalse(hasattr(loaded, "sqlite3"))
        self.assertFalse(hasattr(loaded, "connect"))

    def test_unsupported_granularity_surfaces_timeseries_error(self):
        """D-9 unsupported granularity raises the existing timeseries
        ValueError, not a new error type."""
        with self.assertRaises(ValueError):
            self._projection(granularity="week")


if __name__ == "__main__":
    unittest.main()
