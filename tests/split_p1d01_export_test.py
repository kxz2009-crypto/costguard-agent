"""
P1D-01 OPEN Analytics Export tests.

Covers:
X-EXP-1 summary export echoes analytics fields
X-EXP-2 timeseries export preserves point order
X-EXP-3 distribution export matches visualization output
X-EXP-4 determinism: identical inputs -> byte-identical documents
X-EXP-5 manifest content hash matches payload
X-EXP-6 manifest filters echo inputs
X-EXP-7 export does not mutate database
X-EXP-8 export module imports no db module
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import unittest
from dataclasses import asdict

from costguard_split.export import (
    distribution_export,
    summary_export,
    timeseries_export,
)
from costguard_split.analytics.service import analytics_summary
from costguard_split.analytics.timeseries import timeseries_summary
from costguard_split.visualization.service import (
    model_distribution,
    provider_distribution,
    visualization_summary,
)


def _canonical(document: dict) -> str:
    return json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


class ExportTestBase(unittest.TestCase):

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


class SummaryExportTests(ExportTestBase):

    def test_summary_export_echoes_analytics_fields(self):
        """X-EXP-1 payload equals asdict of the existing analytics summary."""
        direct = analytics_summary(
            self.db, "org-a", "2026-01-01", "2026-01-31"
        )
        document = summary_export(
            self.db, "org-a", "2026-01-01", "2026-01-31"
        )

        self.assertEqual(document.payload, {
            "totals": {
                "events": direct.totals.events,
                "request_count": direct.totals.request_count,
                "input_tokens": direct.totals.input_tokens,
                "cached_input_tokens": direct.totals.cached_input_tokens,
                "cache_write_tokens": direct.totals.cache_write_tokens,
                "output_tokens": direct.totals.output_tokens,
                "reasoning_tokens": direct.totals.reasoning_tokens,
                "public_cost_sum_nullable":
                    direct.totals.public_cost_sum_nullable,
            },
            "by_provider": [
                asdict(item) for item in direct.by_provider
            ],
            "by_model": [
                asdict(item) for item in direct.by_model
            ],
            "by_member": [
                asdict(item) for item in direct.by_member
            ],
            "by_device": [
                asdict(item) for item in direct.by_device
            ],
        })
        self.assertEqual(document.manifest.generated_from, "analytics")


class TimeseriesExportTests(ExportTestBase):

    def test_timeseries_export_preserves_point_order(self):
        """X-EXP-2 point order matches the existing read model exactly."""
        points = timeseries_summary(
            self.db, "org-a", "2026-01-01", "2026-01-31", "day"
        )
        document = timeseries_export(
            self.db, "org-a", "2026-01-01", "2026-01-31", "day"
        )

        self.assertEqual(len(document.payload), len(points))
        for exported, point in zip(document.payload, points):
            self.assertEqual(exported["bucket_start"], point.bucket_start)
            self.assertEqual(exported["bucket_end"], point.bucket_end)
            self.assertEqual(exported["events"], point.events)
            self.assertEqual(exported["input_tokens"], point.input_tokens)
            self.assertEqual(exported["output_tokens"], point.output_tokens)

        self.assertEqual(document.manifest.generated_from, "timeseries")


class DistributionExportTests(ExportTestBase):

    def test_distribution_export_matches_visualization_output(self):
        """X-EXP-3 distributions match the visualization layer output."""
        direct = analytics_summary(
            self.db, "org-a", "2026-01-01", "2026-01-31"
        )
        document = distribution_export(
            self.db, "org-a", "2026-01-01", "2026-01-31"
        )

        expected_summary = visualization_summary(direct)
        self.assertEqual(
            document.payload["summary"]["events"], expected_summary.events)
        self.assertEqual(
            document.payload["summary"]["tokens"], expected_summary.tokens)

        expected_providers = [
            {"dimension": p.dimension, "key": p.key,
             "events": p.events, "tokens": p.tokens}
            for p in provider_distribution(direct)
        ]
        self.assertEqual(
            document.payload["provider_distribution"], expected_providers)

        expected_models = [
            {"dimension": m.dimension, "key": m.key,
             "events": m.events, "tokens": m.tokens}
            for m in model_distribution(direct)
        ]
        self.assertEqual(
            document.payload["model_distribution"], expected_models)


class ExportDeterminismTests(ExportTestBase):

    def test_export_determinism_bytes_identical(self):
        """X-EXP-4 identical inputs produce byte-identical documents."""
        args = ("org-a", "2026-01-01", "2026-01-31")

        first = summary_export(self.db, *args)
        second = summary_export(self.db, *args)

        self.assertEqual(
            _canonical(first.to_dict()), _canonical(second.to_dict()))

        first_ts = timeseries_export(
            self.db, "org-a", "2026-01-01", "2026-01-31", "day")
        second_ts = timeseries_export(
            self.db, "org-a", "2026-01-01", "2026-01-31", "day")
        self.assertEqual(
            _canonical(first_ts.to_dict()), _canonical(second_ts.to_dict()))


class ExportManifestTests(ExportTestBase):

    def test_manifest_content_hash_matches_payload(self):
        """X-EXP-5 content hash is sha256 over canonical payload bytes."""
        document = summary_export(
            self.db, "org-a", "2026-01-01", "2026-01-31"
        )
        expected = hashlib.sha256(
            json.dumps(
                document.payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(document.manifest.content_hash, expected)
        self.assertEqual(document.manifest.schema_version, "1")
        self.assertEqual(document.manifest.baseline, "v0.5.1-p1c02")

    def test_manifest_filters_echo_inputs(self):
        """X-EXP-6 manifest echoes window and filter inputs."""
        document = summary_export(
            self.db,
            "org-a",
            "2026-01-01",
            "2026-01-02",
            provider="claude",
            model="opus",
            member_id="m-1",
            device_id="d-1",
        )
        as_dict = document.to_dict()
        self.assertEqual(
            as_dict["manifest"]["window"],
            {"start": "2026-01-01", "end": "2026-01-02"})
        self.assertEqual(
            as_dict["manifest"]["filters"],
            {
                "provider": "claude",
                "model": "opus",
                "member_id": "m-1",
                "device_id": "d-1",
            })


class ExportBoundaryTests(ExportTestBase):

    def test_export_does_not_mutate_db(self):
        """X-EXP-7 export never writes: row counts and table size stable."""
        before = self.db.execute(
            "SELECT COUNT(*) FROM usage_events").fetchone()[0]

        summary_export(self.db, "org-a", "2026-01-01", "2026-01-31")
        timeseries_export(
            self.db, "org-a", "2026-01-01", "2026-01-31", "day")
        distribution_export(self.db, "org-a", "2026-01-01", "2026-01-31")

        after = self.db.execute(
            "SELECT COUNT(*) FROM usage_events").fetchone()[0]
        self.assertEqual(before, after)
        self.assertEqual(self.db.in_transaction, False)

    def test_export_module_does_not_import_db(self):
        """X-EXP-8 export layer must not import db or sqlite3 modules."""
        import costguard_split.export.service as export_service
        import sys

        source = open(export_service.__file__, encoding="utf-8").read()
        self.assertNotIn("import sqlite3", source)
        self.assertNotIn("from costguard_split.db", source)
        self.assertNotIn("costguard_split.db ", source)

        loaded = sys.modules.get("costguard_split.export.service")
        self.assertIsNotNone(loaded)
        self.assertFalse(hasattr(loaded, "sqlite3"))
        self.assertFalse(hasattr(loaded, "connect"))


if __name__ == "__main__":
    unittest.main()
