"""Split DB connection — <resolved CostGuard home>/split.db, 0600, migrations.

B-2 (single path authority): ALL path resolution lives in
costguard_split.paths. This module keeps no second directory logic —
split_db_path() delegates to paths.split_db_path(), which honors:
    explicit home arg  >  COSTGUARD_HOME  >  legacy ~/.costguard
call-time (no import-time caching), so tests and multi-home tooling can
retarget the database freely without touching the real user home.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from . import paths
from .schemas.tables import apply_migrations

SPLIT_DB_NAME = "split.db"      # re-exported for callers that only need the name


def split_db_path(home: Path | str | None = None) -> Path:
    """Delegate to the single resolver (paths.split_db_path)."""
    return paths.split_db_path(home)


def connect(path: Path | str | None = None,
            home: Path | str | None = None,
            check_same_thread: bool = True) -> sqlite3.Connection:
    """Open (creating if needed) the Split DB with 0600 perms + migrations.

    Precedence: explicit `path` beats everything; otherwise the DB lives at
    split_db_path(home) under the one resolved CostGuard home.

    check_same_thread=False is for long-lived server connections shared
    across worker threads (FastAPI); local CLI usage keeps the default.
    """
    p = Path(path).expanduser() if path else split_db_path(home)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.touch(mode=0o600)
    os.chmod(p, 0o600)  # enforce even if it pre-existed
    db = sqlite3.connect(p, check_same_thread=check_same_thread)
    db.execute("PRAGMA foreign_keys = ON")
    apply_migrations(db)
    return db
