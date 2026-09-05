"""Free Beta v0.2 tests: pricing, HTML report, packaging metadata, data delete."""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from costguard_agent.pricing import PriceTable, cost_usd, UNPRICED


class PricingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pt = PriceTable.load_builtin()

    def test_table_loads_with_version(self):
        self.assertGreater(len(self.pt.table_version), 4)
        self.assertGreater(self.pt.known_aliases, 10)

    def test_alias_resolution(self):
        # real-world raw names from the live dataset
        for raw, expected in [("k3", "kimi-k3"),
                              ("custom:gpt-5.5/gpt-5.5", "gpt-5.5"),
                              ("chat2api-bridge/gpt-plus", "gpt-plus"),
                              ("gpt-5.6-sol", "gpt-5.6"),
                              ("qwen3.8:27b", "qwen3.8-27b")]:
            p = self.pt.lookup(raw)
            self.assertIsNotNone(p, raw)
            self.assertEqual(p.canonical, expected)

    def test_unknown_model_is_unpriced_not_zero(self):
        self.assertIsNone(self.pt.lookup("totally-unknown-model"))
        self.assertIsNone(self.pt.lookup(""))
        # normalize keeps unknown names verbatim (never guesses)
        self.assertEqual(self.pt.normalize("mystery-model"), "mystery-model")

    def test_cost_math(self):
        p = self.pt.lookup("gpt-5.5")
        # 1M input @1.25 + 1M output @10.0 = 11.25
        self.assertEqual(cost_usd(p, 1_000_000, 1_000_000), 11.25)
        # zero-price local models are legitimately 0.0 but PRICED
        p2 = self.pt.lookup("qwen3.8:27b")
        self.assertIsNotNone(p2)
        self.assertEqual(cost_usd(p2, 5_000_000, 1_000_000), 0.0)

    def test_report_cost_section_integration(self):
        from costguard_agent.reports import build_report
        rep = build_report()
        if rep["total_tokens"] == 0:
            self.skipTest("no local data")
        c = rep["cost"]
        self.assertIn("local_estimate", c)
        self.assertIn("price_table_version", c)
        # unknown models are listed, never silently $0
        self.assertIsInstance(c["unpriced_models"], list)


class HtmlReportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from costguard_agent.reports import build_report
        from costguard_agent.html_report import render_html
        cls.rep = build_report()
        cls.html = render_html(cls.rep, generated_at="2026-09-05T00:00:00+00:00")

    def test_contains_all_sections(self):
        for needle in ("By Source", "By Provider", "Model Share",
                       "Cost Estimate", "Privacy:", "unknown"):
            self.assertIn(needle, self.html)

    def test_offline_selfcontained(self):
        self.assertNotIn("<script", self.html)
        self.assertNotIn("http://", self.html)
        self.assertNotIn("https://", self.html)
        self.assertNotIn("src=", self.html)
        self.assertNotIn("link rel", self.html)

    def test_escaping(self):
        from costguard_agent.html_report import render_html
        evil = {"date": "2026-01-01", "total_tokens": 1,
                "by_source": {"<script>alert(1)</script>": {
                    "tokens": 1, "events": 1, "share_pct": 100.0}},
                "model_share": [], "cost": {},
                "schema_version": 1}
        out = render_html(evil)
        self.assertNotIn("<script>alert", out)
        self.assertIn("&lt;script&gt;", out)

    def test_unknown_never_zero_display(self):
        # when there are unpriced models, page says unknown explicitly
        if self.rep.get("cost", {}).get("unknown_events", 0) > 0:
            self.assertIn("unknown", self.html)
            self.assertIn("never counted", self.html)


class PackagingTest(unittest.TestCase):
    def test_pyproject_metadata(self):
        try:
            import tomllib
        except ImportError:  # py<3.11
            import tomli as tomllib
        root = Path(__file__).resolve().parents[1]
        t = tomllib.loads((root / "pyproject.toml").read_text())
        self.assertEqual(t["project"]["name"], "costguard-agent")
        self.assertTrue(str(t["project"]["version"]).startswith("0.2.0"))
        self.assertIn("readme", t["project"])
        self.assertEqual(t["project"]["requires-python"], ">=3.10")
        self.assertEqual(t["project"]["dependencies"], [])
        self.assertTrue((root / "README.md").exists())
        self.assertTrue((root / "LICENSE").exists())

    def test_data_files_ship_in_package(self):
        from costguard_agent import pricing
        import costguard_agent.data as data_pkg
        self.assertTrue(data_pkg.__file__)
        # builtin table actually loads from packaged data
        pt = PriceTable.load_builtin()
        self.assertGreater(pt.known_aliases, 10)


class DataDeleteTest(unittest.TestCase):
    def test_delete_removes_isolated_home(self):
        import shutil
        from costguard_agent import database
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / ".costguard"
            fake.mkdir()
            (fake / "x.db").write_text("x")
            real_dir = database.CG_DIR
            try:
                database.CG_DIR = fake  # point cmd_data at isolated dir
                from costguard_agent import cli
                code = cli.cmd_data(type("A", (), {"yes": True})())
                self.assertEqual(code, 0)
                self.assertFalse(fake.exists())
            finally:
                database.CG_DIR = real_dir


if __name__ == "__main__":
    unittest.main(verbosity=2)
