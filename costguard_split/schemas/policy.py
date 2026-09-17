"""Split code/schema policy guards (PATCH 9).

Number-type policy, locked from P0 (billing arrives in P2):
- token counters : INTEGER  (PostgreSQL: BIGINT)
- money          : Decimal  (PostgreSQL: NUMERIC(12,4) or finer)
- FORBIDDEN for cost/price/allocation/settlement: float, REAL, DOUBLE.

guard_money_columns(conn) is a runtime guard; tests additionally run the
static scan in tests/split_hardening_test.py so a bad migration can never
land. This is intentionally NOT a P2 implementation.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_MONEY_HINTS = ("cost", "price", "allocation", "settlement", "amount",
                "balance")
_FORBIDDEN_TYPES = ("REAL", "FLOAT", "DOUBLE")


def guard_money_columns(conn: sqlite3.Connection) -> list[str]:
    """Scan live schema: any REAL/FLOAT/DOUBLE column whose name hints at
    money is a policy violation. Returns violation descriptions."""
    violations: list[str] = []
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
        " AND name NOT LIKE 'sqlite_%'")]
    for table in tables:
        for col in conn.execute(f"PRAGMA table_info({table})"):
            name, decl = col[1], (col[2] or "").upper()
            if any(h in name.lower() for h in _MONEY_HINTS) and any(
                    f in decl for f in _FORBIDDEN_TYPES):
                violations.append(f"{table}.{name} {decl}")
    return violations


def guard_source_tree_static(root: Path) -> list[str]:
    """Static scan of Split sources: float/REAL/DOUBLE used near money
    identifiers. Heuristic, cheap, and fails loudly on violations."""
    violations: list[str] = []
    patterns = ("cost", "price", "allocation", "settlement", "amount")
    for py in sorted(Path(root).rglob("*.py")):
        lines = py.read_text(encoding="utf-8").splitlines()
        in_doc = False
        for i, line in enumerate(lines, 1):
            s = line.strip()
            if s.startswith('"""'):
                in_doc = not in_doc if s.count('"""') == 1 else in_doc
                continue
            if in_doc or s.startswith("#"):
                continue  # comments/docstrings are not executable policy
            low = s.lower()
            if any(h in low for h in patterns) and any(
                    t in low for t in ("float(", " real", "double",
                                       ": float", "-> float")):
                violations.append(f"{py.name}:{i}: {s[:80]}")
    return violations
