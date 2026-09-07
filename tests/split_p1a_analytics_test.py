"""
P1B-01 OPEN Analytics Read Model tests.

Covers:
A1 aggregation correctness
A2 half-open boundary
A3 started_at semantics
A4 NULL member grouping
A5 NULL money handling
A6 organization isolation
A7 usage_events immutable
A8 no raw content exposure
A9 no PRIVATE intelligence symbols
"""

from __future__ import annotations

import sqlite3
import unittest

from costguard_split.analytics.service import analytics_summary


class AnalyticsTest(unittest.TestCase):

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

        self.db.executemany("""
        INSERT INTO usage_events VALUES
        (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (
                "1", "org-a", "claude", "m1",
                "member-a", "device-a",
                "2026-01-01T00:00:00",
                2, 10, 1, 0, 5, 3, "1.2500"
            ),
            (
                "2", "org-a", "codex", "m2",
                None, "device-b",
                "2026-01-02T00:00:00",
                1, 20, 0, 0, 8, 0, None
            ),
            (
                "3", "org-b", "claude", "m1",
                "member-x", "device-x",
                "2026-01-01T00:00:00",
                99, 999, 0, 0, 0, 0, "99"
            ),
        ])

    def tearDown(self):
        self.db.close()

    def test_a1_aggregation_correctness(self):
        result = analytics_summary(
            self.db,
            "org-a",
            "2026-01-01T00:00:00",
            "2026-01-03T00:00:00",
        )

        self.assertEqual(result.totals.events, 2)
        self.assertEqual(result.totals.request_count, 3)
        self.assertEqual(result.totals.input_tokens, 30)

    def test_a2_half_open_boundary(self):
        result = analytics_summary(
            self.db,
            "org-a",
            "2026-01-01T00:00:00",
            "2026-01-02T00:00:00",
        )

        self.assertEqual(result.totals.events, 1)

    def test_a3_started_at_semantics(self):
        result = analytics_summary(
            self.db,
            "org-a",
            "2026-01-02T00:00:00",
            "2026-01-03T00:00:00",
        )

        self.assertEqual(result.totals.events, 1)

    def test_a4_null_member(self):
        result = analytics_summary(
            self.db,
            "org-a",
            "2026-01-01T00:00:00",
            "2026-01-03T00:00:00",
        )

        keys = [x.key for x in result.by_member]
        self.assertIn("", keys)

    def test_a5_null_money(self):
        result = analytics_summary(
            self.db,
            "org-a",
            "2026-01-01T00:00:00",
            "2026-01-03T00:00:00",
        )

        self.assertIsNone(
            result.totals.public_cost_sum_nullable
        )

    def test_a6_org_isolation(self):
        result = analytics_summary(
            self.db,
            "org-a",
            "2026-01-01T00:00:00",
            "2026-01-03T00:00:00",
        )

        self.assertEqual(result.totals.events, 2)

    def test_a7_no_mutation(self):
        before = self.db.execute(
            "SELECT count(*) FROM usage_events"
        ).fetchone()[0]

        analytics_summary(
            self.db,
            "org-a",
            "2026-01-01T00:00:00",
            "2026-01-03T00:00:00",
        )

        after = self.db.execute(
            "SELECT count(*) FROM usage_events"
        ).fetchone()[0]

        self.assertEqual(before, after)

    def test_a8_no_raw_content(self):
        result = analytics_summary(
            self.db,
            "org-a",
            "2026-01-01T00:00:00",
            "2026-01-03T00:00:00",
        )

        self.assertNotIn(
            "prompt",
            repr(result).lower()
        )

    def test_a9_no_private_symbols(self):
        from pathlib import Path

        text = Path(
            "costguard_split/analytics/service.py"
        ).read_text()

        forbidden = [
            "recommendation",
            "optimization",
            "reconciliation",
            "quota",
            "allocation",
        ]

        for word in forbidden:
            self.assertNotIn(word, text.lower())


if __name__ == "__main__":
    unittest.main()
