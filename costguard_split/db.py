"""Split DB connection — separate file, same local data directory.

Reuses costguard_agent's storage-location convention WITHOUT hardcoding a
path: database.CG_DIR is read at call time (module attribute), so tests can
patch it exactly the way existing CostGuard tests do. Split keeps its own
SQLite file (split.db) so Agent and Split schemas never collide and either
can move to PostgreSQL independently later.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from ._compat import agent_database  # lazy agent import, see below
from .schemas.tables import apply_migrations

SPLIT_DB_NAME = "split.db"


def split_db_path() -> Path:
    """Resolve <agent data dir>/split.db at call time (no hardcode)."""
    return agent_database().CG_DIR / SPLIT_DB_NAME


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Open (creating if needed) the Split DB with 0600 perms + migrations."""
    p = Path(path) if path else split_db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.touch(mode=0o600)
    os.chmod(p, 0o600)  # enforce even if it pre-existed
    db = sqlite3.connect(p)
    db.execute("PRAGMA foreign_keys = ON")
    apply_migrations(db)
    return db
