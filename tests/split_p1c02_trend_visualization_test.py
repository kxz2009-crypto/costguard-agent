"""
P1C-02 OPEN Trend Visualization API tests.

Covers:
V1 trend returns TimeSeries DTO
V2 daily trend
V3 hourly trend
V4 half-open interval
V5 organization isolation
V6 NULL cost preservation
V7 no mutation
V8 no raw content exposure
V9 no private intelligence symbols
"""

from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from costguard_split.api.app import create_app
from costguard_split.api.context import ServerContext


class TrendVisualizationTest(unittest.TestCase):

    def setUp(self):
        self.db = sqlite3.connect(
            ":memory:",
            check_same_thread=False,
        )
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
                    1,
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
                    "2026-01-01T01:00:00",
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

        self.app = create_app(
            context=ServerContext(
                organization_id="org-a"
            )
        )

        # replace internal db dependency for test
        import costguard_split.api.app as api_app
        self._orig_connect_db = api_app.connect_db
        api_app.connect_db = lambda *a, **k: self.db

        self.app = create_app(
            context=ServerContext(
                organization_id="org-a"
            )
        )

        self.client = TestClient(self.app)


    def tearDown(self):
        # restore the module-level connect_db so later test modules
        # build real apps (leaking this patch would hand every later
        # create_app() this closed in-memory db)
        import costguard_split.api.app as api_app
        api_app.connect_db = self._orig_connect_db
        self.db.close()


    def test_v1_returns_dto_shape(self):
        r = self.client.get(
            "/api/v1/visualization/trend",
            params={
                "org_id": "org-a",
                "start": "2026-01-01T00:00:00",
                "end": "2026-01-02T00:00:00",
                "interval": "day",
            },
        )

        self.assertEqual(r.status_code, 200)
        body = r.json()

        self.assertIn("bucket_start", body[0])
        self.assertIn("events", body[0])


    def test_v2_daily(self):
        r = self.client.get(
            "/api/v1/visualization/trend",
            params={
                "org_id": "org-a",
                "start": "2026-01-01T00:00:00",
                "end": "2026-01-02T00:00:00",
                "interval": "day",
            },
        )

        self.assertEqual(r.json()[0]["events"], 2)


    def test_v3_hourly(self):
        r = self.client.get(
            "/api/v1/visualization/trend",
            params={
                "org_id": "org-a",
                "start": "2026-01-01T00:00:00",
                "end": "2026-01-01T02:00:00",
                "interval": "hour",
            },
        )

        self.assertEqual(len(r.json()), 2)


    def test_v4_half_open(self):
        r = self.client.get(
            "/api/v1/visualization/trend",
            params={
                "org_id": "org-a",
                "start": "2026-01-01T00:00:00",
                "end": "2026-01-01T01:00:00",
                "interval": "hour",
            },
        )

        self.assertEqual(
            r.json()[0]["events"],
            1,
        )


    def test_v5_org_isolation(self):
        r = self.client.get(
            "/api/v1/visualization/trend",
            params={
                "org_id": "org-b",
                "start": "2026-01-01T00:00:00",
                "end": "2026-01-02T00:00:00",
                "interval": "day",
            },
        )

        self.assertEqual(r.status_code, 404)


    def test_v6_null_cost(self):
        r = self.client.get(
            "/api/v1/visualization/trend",
            params={
                "org_id": "org-a",
                "start": "2026-01-01T00:00:00",
                "end": "2026-01-02T00:00:00",
                "interval": "day",
            },
        )

        self.assertIsNone(
            r.json()[0]["public_cost_nullable"]
        )


    def test_v7_no_mutation(self):
        before = self.db.execute(
            "select count(*) from usage_events"
        ).fetchone()[0]

        self.client.get(
            "/api/v1/visualization/trend",
            params={
                "org_id": "org-a",
                "start": "2026-01-01T00:00:00",
                "end": "2026-01-02T00:00:00",
                "interval": "day",
            },
        )

        after = self.db.execute(
            "select count(*) from usage_events"
        ).fetchone()[0]

        self.assertEqual(before, after)


    def test_v8_no_raw_content(self):
        text = str(
            self.client.get(
                "/api/v1/visualization/trend",
                params={
                    "org_id": "org-a",
                    "start": "2026-01-01T00:00:00",
                    "end": "2026-01-02T00:00:00",
                    "interval": "day",
                },
            ).json()
        )

        self.assertNotIn(
            "prompt",
            text.lower(),
        )


    def test_v9_no_private_symbols(self):
        text = Path(
            "costguard_split/api/trend_visualization.py"
        ).read_text().lower()

        for word in [
            "recommendation",
            "optimization",
            "forecast",
            "quota",
            "allocation",
        ]:
            self.assertNotIn(word, text)


if __name__ == "__main__":
    unittest.main()
