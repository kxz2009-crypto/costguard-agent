"""Free Beta P0 UX tests: first-run experience in empty environments.

Run: python -m unittest tests.p0_ux_test
Covers:
  U1  scan in an environment with no AI tools -> guided empty state
      (mentions no-data reason, supported tools, coming-soon, next step)
  U2  report with empty DB -> three-part empty state
      (reason / supported tools / next step), exit code 1 preserved
  U3  report --html empty DB -> same guidance, still writes no junk,
      exit code 1 preserved
  U4  --help advertises supported connectors incl. coming-soon
Isolation: database.CG_DIR/DB_PATH patched to a temp dir (same pattern as
DataDeleteTest). No real ~/.costguard is touched.
"""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from costguard_agent import database  # noqa: E402
from costguard_agent import cli  # noqa: E402


class _IsolatedHome:
    """Point CostGuard storage AND connector discovery at a temp dir.

    Patches database.CG_DIR/DB_PATH (same pattern as DataDeleteTest) and
    each connector's allowed_paths so scan() behaves as if no AI tool is
    installed, regardless of the host machine.
    """

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        cg = Path(self._tmp.name) / ".costguard"
        self._old = (database.CG_DIR, database.DB_PATH)
        database.CG_DIR = cg
        database.DB_PATH = cg / "costguard.db"
        self._old_paths = []
        from costguard_agent.connectors import hermes, codex
        for mod in (hermes, codex):
            self._old_paths.append((mod.HermesConnector if mod is hermes
                                    else mod.CodexConnector,
                                    mod.HermesConnector.allowed_paths
                                    if mod is hermes
                                    else mod.CodexConnector.allowed_paths))
        hermes.HermesConnector.allowed_paths = (
            str(Path(self._tmp.name) / ".hermes" / "state.db"),)
        codex.CodexConnector.allowed_paths = (
            str(Path(self._tmp.name) / ".codex" / "state_5.sqlite"),)
        return self

    def __exit__(self, *exc):
        database.CG_DIR, database.DB_PATH = self._old
        for cls, paths in self._old_paths:
            cls.allowed_paths = paths
        self._tmp.cleanup()
        return False


def _run_cli(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli.main(argv)
    return code, buf.getvalue()


class ScanEmptyTest(unittest.TestCase):
    def test_u1_scan_empty_state_is_guided(self):
        with _IsolatedHome():
            code, out = _run_cli(["scan"])
        self.assertEqual(code, 0)
        # reason: no AI usage data found
        self.assertIn("No AI usage data found", out)
        # supported tools listed
        self.assertIn("hermes", out)
        self.assertIn("codex", out)
        # checked paths shown
        self.assertIn(".hermes/state.db", out)
        self.assertIn(".codex/sqlite/state_5.sqlite", out)
        # coming-soon signpost
        self.assertIn("Claude Code", out)
        self.assertIn("coming soon", out)
        # next step
        self.assertIn("costguard scan", out)  # referenced as how to refresh


class ReportEmptyTest(unittest.TestCase):
    def test_u2_report_empty_three_parts(self):
        with _IsolatedHome():
            code, out = _run_cli(["report"])
        self.assertEqual(code, 1)  # unchanged exit semantics
        # part 1: reason
        self.assertIn("No AI usage data found", out)
        # part 2: supported tools
        self.assertIn("Hermes", out)
        self.assertIn("Codex", out)
        # part 3: next step
        self.assertIn("costguard scan", out)

    def test_u3_report_html_empty_writes_file_and_guides(self):
        with _IsolatedHome():
            out_path = Path(database.CG_DIR) / "exports" / "report.html"
            code, out = _run_cli(
                ["report", "--html", "--out", str(out_path)])
            self.assertEqual(code, 1)  # unchanged exit semantics
            self.assertIn("No AI usage data found", out)
            self.assertIn("coming soon", out)
            # html file still written (unchanged behavior) and 0600
            self.assertTrue(out_path.exists())
            self.assertEqual(oct(out_path.stat().st_mode & 0o777), "0o600")


class HelpTest(unittest.TestCase):
    def test_u4_help_lists_connectors(self):
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                cli.main(["--help"])
        except SystemExit as e:
            self.assertEqual(e.code, 0)
        out = buf.getvalue()
        self.assertIn("Supported connectors", out)
        self.assertIn("Hermes", out)
        self.assertIn("Codex", out)
        self.assertIn("Claude Code (coming soon)", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
