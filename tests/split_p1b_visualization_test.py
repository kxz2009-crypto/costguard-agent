"""P1B-02 OPEN visualization acceptance tests."""

from __future__ import annotations

import unittest

from costguard_split.analytics.dto import (
    AnalyticsSummary,
    DimensionSummary,
    UsageTotals,
)

from costguard_split.visualization.service import (
    model_distribution,
    provider_distribution,
    visualization_summary,
)


class VisualizationTest(unittest.TestCase):

    def _analytics(self):
        return AnalyticsSummary(
            totals=UsageTotals(
                events=10,
                request_count=12,
                input_tokens=100,
                cached_input_tokens=20,
                cache_write_tokens=5,
                output_tokens=50,
                reasoning_tokens=25,
                public_cost_sum_nullable="0.1234",
            ),
            by_provider=[
                DimensionSummary(
                    key="openai",
                    events=6,
                    request_count=7,
                    input_tokens=50,
                    output_tokens=20,
                )
            ],
            by_model=[
                DimensionSummary(
                    key="model-a",
                    events=10,
                    request_count=12,
                    input_tokens=100,
                    output_tokens=50,
                )
            ],
        )

    # V1/V3
    def test_v1_summary_projection(self):
        result = visualization_summary(self._analytics())

        self.assertEqual(result.events, 10)
        self.assertEqual(result.tokens, 200)
        self.assertEqual(
            result.public_cost_nullable,
            "0.1234",
        )

    # V2
    def test_v2_provider_distribution(self):
        result = provider_distribution(self._analytics())

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].dimension, "provider")
        self.assertEqual(result[0].key, "openai")
        self.assertEqual(result[0].tokens, 70)

    # V2
    def test_v3_model_distribution(self):
        result = model_distribution(self._analytics())

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].dimension, "model")
        self.assertEqual(result[0].key, "model-a")

    # V4
    def test_v4_null_cost_preserved(self):
        analytics = self._analytics()

        analytics = AnalyticsSummary(
            totals=UsageTotals(
                events=1,
                public_cost_sum_nullable=None,
            )
        )

        result = visualization_summary(analytics)

        self.assertIsNone(
            result.public_cost_nullable
        )

    # V5/V6
    def test_v5_read_only_projection(self):
        analytics = self._analytics()

        before = analytics

        visualization_summary(analytics)
        provider_distribution(analytics)

        self.assertEqual(
            analytics,
            before,
        )

    # V7/V8/V9 static boundary checks
    def test_v6_no_forbidden_symbols(self):
        from pathlib import Path

        text = ""

        for p in Path(
            "costguard_split/visualization"
        ).glob("*.py"):
            text += p.read_text()

        forbidden = [
            "usage_events",
            "SELECT",
            "billing",
            "quota",
            "allocation",
            "optimization",
            "recommendation",
        ]

        for word in forbidden:
            self.assertNotIn(word, text)


if __name__ == "__main__":
    unittest.main()
