"""P1B-03 OPEN visualization API acceptance tests."""

from __future__ import annotations

import unittest

from costguard_split.api.visualization import _check_org


class VisualizationAPITest(unittest.TestCase):

    def test_a1_org_scope_allowed(self):
        class C:
            organization_id = "org-1"

        self.assertIsNone(
            _check_org(C(), "org-1")
        )

    def test_a2_cross_org_hidden(self):
        class C:
            organization_id = "org-1"

        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as ctx:
            _check_org(C(), "org-2")

        self.assertEqual(ctx.exception.status_code, 404)

    def test_a3_no_private_symbols(self):
        from pathlib import Path

        text = Path(
            "costguard_split/api/visualization.py"
        ).read_text()

        forbidden = [
            "billing",
            "quota",
            "allocation",
            "optimization",
            "recommendation",
        ]

        for word in forbidden:
            self.assertNotIn(word, text)

    def test_a4_no_sql_dependency(self):
        from pathlib import Path

        text = Path(
            "costguard_split/api/visualization.py"
        ).read_text()

        self.assertNotIn("SELECT", text)
        self.assertNotIn("execute(", text)

    def test_a5_trend_not_exposed(self):
        from pathlib import Path

        text = Path(
            "costguard_split/api/visualization.py"
        ).read_text()

        self.assertNotIn(
            "/visualization/trend",
            text,
        )


if __name__ == "__main__":
    unittest.main()
