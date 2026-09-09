"""
P1D-03 OPEN Report Generation tests.

Covers:
R-1 summary report totals match analytics
R-2 summary report distributions match visualization
R-3 timeseries report rows match timeseries order
R-4 determinism: identical inputs -> byte-identical text
R-5 envelope content_hash matches body
R-6 meta completeness
R-7 org isolation
R-8 report does not mutate db
R-9 module boundaries (no db / sqlite3 / file writes)
R-10 no interpretation vocabulary
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import unittest
from dataclasses import asdict

from costguard_split.analytics.service import analytics_summary
from costguard_split.analytics.timeseries import timeseries_summary
from costguard_split.report import summary_report, timeseries_report
from costguard_split.visualization.service import (
    model_distribution,
    provider_distribution,
    visualization_summary,
)

BANNED_VOCABULARY = ("trend", "spike", "anomal", "recommend")


def _body_hash(body: str) -> str:
    return hashlib.sha256(
        json.dumps(
            body,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


class ReportTestBase(unittest.TestCase):

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


class SummaryReportTests(ReportTestBase):

    def test_summary_report_totals_match_analytics(self):
        """R-1 totals row equals visualization_summary output."""
        direct = analytics_summary(
            self.db, "org-a", "2026-01-01", "2026-01-31")
        expected = visualization_summary(direct)

        document = summary_report(
            self.db, "org-a", "2026-01-01", "2026-01-31")

        totals_line = [
            line for line in document.body.splitlines()
            if line.startswith("|") and str(expected.events) in line
        ][0]
        self.assertEqual(
            totals_line,
            f"| {expected.events} | {expected.tokens} | "
            f"{expected.public_cost_nullable if expected.public_cost_nullable is not None else ''} |")

    def test_summary_report_distributions_match_visualization(self):
        """R-2 provider/model rows equal visualization layer output."""
        direct = analytics_summary(
            self.db, "org-a", "2026-01-01", "2026-01-31")
        providers = [asdict(p) for p in provider_distribution(direct)]
        models = [asdict(m) for m in model_distribution(direct)]

        document = summary_report(
            self.db, "org-a", "2026-01-01", "2026-01-31")
        lines = document.body.splitlines()

        for point in providers:
            row = f"| {point['key']} | {point['events']} | {point['tokens']} |"
            self.assertIn(row, lines)
        for point in models:
            row = f"| {point['key']} | {point['events']} | {point['tokens']} |"
            self.assertIn(row, lines)

    def test_summary_report_renders_none_as_empty(self):
        """Nullable cells render as empty cells, not 'None'."""
        document = summary_report(
            self.db, "org-a", "2026-01-01", "2026-01-31")
        self.assertNotIn("| None |", document.body)
        self.assertNotIn("None", document.body)


class TimeseriesReportTests(ReportTestBase):

    def test_timeseries_report_rows_match_timeseries_order(self):
        """R-3 one row per point, exact source order."""
        direct = timeseries_summary(
            self.db, organization_id="org-a",
            start="2026-01-01", end="2026-01-31", granularity="day")

        document = timeseries_report(
            self.db, "org-a", "2026-01-01", "2026-01-31", "day")
        lines = document.body.splitlines()

        row_lines = [
            line for line in lines
            if line.startswith("|") and "---" not in line
        ]
        # drop header row
        data_rows = row_lines[1:]
        self.assertEqual(len(data_rows), len(direct))
        for row, point in zip(data_rows, direct):
            d = asdict(point)
            expected = (
                f"| {d['bucket_start']} | {d['bucket_end']} | "
                f"{d['events']} | {d['request_count']} |")
            self.assertTrue(row.startswith(expected), row)

    def test_unsupported_granularity_surfaces_timeseries_error(self):
        """Unsupported granularity raises the existing ValueError."""
        with self.assertRaises(ValueError):
            timeseries_report(
                self.db, "org-a", "2026-01-01", "2026-01-31", "week")


class ReportIntegrityTests(ReportTestBase):

    def test_report_determinism_bytes_identical(self):
        """R-4 identical inputs produce byte-identical documents."""
        args = ("org-a", "2026-01-01", "2026-01-31")
        first = summary_report(self.db, *args)
        second = summary_report(self.db, *args)
        self.assertEqual(first.body, second.body)
        self.assertEqual(first.to_dict(), second.to_dict())

        first_ts = timeseries_report(
            self.db, "org-a", "2026-01-01", "2026-01-31", "day")
        second_ts = timeseries_report(
            self.db, "org-a", "2026-01-01", "2026-01-31", "day")
        self.assertEqual(first_ts.to_dict(), second_ts.to_dict())

    def test_envelope_content_hash_matches_body(self):
        """R-5 content hash equals sha256 over canonical body bytes."""
        document = summary_report(
            self.db, "org-a", "2026-01-01", "2026-01-31")
        self.assertEqual(
            document.content_hash, _body_hash(document.body))
        self.assertEqual(document.meta.schema_version, "1")
        self.assertEqual(document.meta.baseline, "v0.6.1-p1d02")

    def test_meta_completeness(self):
        """R-6 meta carries window, granularity and filter echo."""
        document = summary_report(
            self.db,
            "org-a",
            "2026-01-01",
            "2026-01-02",
            provider="claude",
            model="opus",
            member_id="member-a",
            device_id="device-a",
        )
        as_dict = document.to_dict()
        self.assertEqual(
            as_dict["meta"]["window"],
            {"start": "2026-01-01", "end": "2026-01-02"})
        self.assertIsNone(as_dict["meta"]["granularity"])
        self.assertEqual(
            as_dict["meta"]["filters"],
            {
                "provider": "claude",
                "model": "opus",
                "member_id": "member-a",
                "device_id": "device-a",
            })

        ts_document = timeseries_report(
            self.db, "org-a", "2026-01-01", "2026-01-02", "hour")
        self.assertEqual(
            ts_document.to_dict()["meta"]["granularity"], "hour")


class ReportBoundaryTests(ReportTestBase):

    def test_org_isolation(self):
        """R-7 events from other organizations never appear."""
        document = summary_report(
            self.db, "org-a", "2026-01-01", "2026-01-31")
        # org-b total is 9 requests; none may leak into org-a report.
        self.assertNotIn("| 9 ", document.body)

    def test_report_does_not_mutate_db(self):
        """R-8 rendering never writes."""
        before = self.db.execute(
            "SELECT COUNT(*) FROM usage_events").fetchone()[0]

        summary_report(self.db, "org-a", "2026-01-01", "2026-01-31")
        timeseries_report(
            self.db, "org-a", "2026-01-01", "2026-01-31", "day")

        after = self.db.execute(
            "SELECT COUNT(*) FROM usage_events").fetchone()[0]
        self.assertEqual(before, after)
        self.assertFalse(self.db.in_transaction)

    def test_module_boundaries(self):
        """R-9 report modules import no db module, no sqlite3, and
        perform no file writes."""
        import costguard_split.report.service as service
        import sys

        source = open(service.__file__, encoding="utf-8").read()
        self.assertNotIn("import sqlite3", source)
        self.assertNotIn("from costguard_split.db", source)
        # no file open/write calls (docstrings excluded by stripping quotes text)
        code_only = "\n".join(
            line for line in source.splitlines()
            if not line.strip().startswith(("#", '"', "'"))
        )
        self.assertNotIn("open(", code_only)
        self.assertNotIn(".write(", code_only)
        self.assertNotIn("Path(", code_only)

        loaded = sys.modules.get("costguard_split.report.service")
        self.assertIsNotNone(loaded)
        self.assertFalse(hasattr(loaded, "sqlite3"))

    def test_no_interpretation_vocabulary(self):
        """R-10 body contains no judgement vocabulary."""
        for document in (
            summary_report(self.db, "org-a", "2026-01-01", "2026-01-31"),
            timeseries_report(
                self.db, "org-a", "2026-01-01", "2026-01-31", "day"),
        ):
            lowered = document.body.lower()
            for word in BANNED_VOCABULARY:
                self.assertNotIn(word, lowered)


if __name__ == "__main__":
    unittest.main()
