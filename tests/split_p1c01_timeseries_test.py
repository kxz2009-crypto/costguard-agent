"""
P1C-01 OPEN Time Series Analytics tests.

Covers:
T1 daily aggregation
T2 hourly aggregation
T3 half-open interval
T4 organization isolation
T5 NULL cost preservation
T6 no mutation
T7 no raw content
T8 no intelligence symbols
"""

from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

from costguard_split.analytics.timeseries import (
    timeseries_summary,
)


class TimeSeriesTest(unittest.TestCase):

    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row

        self.db.execute("""
        CREATE TABLE usage_events (
            id TEXT PRIMARY KEY,
            organization_id TEXT,
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
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "1",
                    "org-a",
                    "2026-01-01T00:30:00",
                    2,
                    10,
                    0,
                    0,
                    5,
                    1,
                    "1.0000",
                ),
                (
                    "2",
                    "org-a",
                    "2026-01-01T01:30:00",
                    1,
                    20,
                    0,
                    0,
                    8,
                    2,
                    None,
                ),
                (
                    "3",
                    "org-b",
                    "2026-01-01T00:30:00",
                    99,
                    999,
                    0,
                    0,
                    0,
                    0,
                    "99",
                ),
            ],
        )

    def tearDown(self):
        self.db.close()

    def test_t1_daily(self):
        result = timeseries_summary(
            self.db,
            "org-a",
            "2026-01-01T00:00:00",
            "2026-01-02T00:00:00",
            "day",
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].events, 2)
        self.assertEqual(result[0].input_tokens, 30)

    def test_t2_hourly(self):
        result = timeseries_summary(
            self.db,
            "org-a",
            "2026-01-01T00:00:00",
            "2026-01-01T02:00:00",
            "hour",
        )

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].events, 1)
        self.assertEqual(result[1].events, 1)

    def test_t3_half_open(self):
        result = timeseries_summary(
            self.db,
            "org-a",
            "2026-01-01T00:00:00",
            "2026-01-01T01:00:00",
            "hour",
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].events, 1)

    def test_t4_org_isolation(self):
        result = timeseries_summary(
            self.db,
            "org-a",
            "2026-01-01T00:00:00",
            "2026-01-02T00:00:00",
            "day",
        )

        self.assertEqual(result[0].events, 2)

    def test_t5_null_cost(self):
        result = timeseries_summary(
            self.db,
            "org-a",
            "2026-01-01T00:00:00",
            "2026-01-02T00:00:00",
            "day",
        )

        self.assertIsNone(
            result[0].public_cost_nullable
        )

    def test_t6_no_mutation(self):
        before = self.db.execute(
            "select count(*) from usage_events"
        ).fetchone()[0]

        timeseries_summary(
            self.db,
            "org-a",
            "2026-01-01T00:00:00",
            "2026-01-02T00:00:00",
            "day",
        )

        after = self.db.execute(
            "select count(*) from usage_events"
        ).fetchone()[0]

        self.assertEqual(before, after)

    def test_t7_no_raw_content(self):
        result = timeseries_summary(
            self.db,
            "org-a",
            "2026-01-01T00:00:00",
            "2026-01-02T00:00:00",
            "day",
        )

        self.assertNotIn(
            "prompt",
            repr(result).lower()
        )

    def test_t8_no_private_symbols(self):
        text = Path(
            "costguard_split/analytics/timeseries.py"
        ).read_text().lower()

        for word in [
            "recommendation",
            "optimization",
            "quota",
            "allocation",
        ]:
            self.assertNotIn(word, text)


if __name__ == "__main__":
    unittest.main()
