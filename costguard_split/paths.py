"""CostGuard home resolution — single place, call-time, no import-time path.

Priority (hardening PATCH 2):
    1. explicit argument (function parameter)      — tests / embedding
    2. COSTGUARD_HOME environment variable         — users / CI
    3. legacy default: agent's CG_DIR (~/.costguard)

Rules:
- resolve_home() is the ONLY way anything in costguard_split finds the
  data directory. Module import must NOT cache a host path (a module-level
  constant would break tests and multi-home tooling); everything resolves
  at call time or receives an explicit Path.
- The agent's own modules (database.CG_DIR etc.) are untouched: Split code
  never reads them for paths anymore; _compat remains for version info.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_NAME = "COSTGUARD_HOME"


def resolve_home(explicit: Path | str | None = None) -> Path:
    """Resolve the CostGuard home directory (call-time)."""
    if explicit is not None:
        return Path(explicit).expanduser()
    env = os.environ.get(ENV_NAME)
    if env:
        return Path(env).expanduser()
    from . import _compat
    return _compat.agent_database().CG_DIR      # legacy default (~/.costguard)


def device_json_path(home: Path | str | None = None) -> Path:
    return resolve_home(home) / "device.json"


def split_db_path(home: Path | str | None = None) -> Path:
    return resolve_home(home) / "split.db"


def fingerprint_key_path(home: Path | str | None = None) -> Path:
    return resolve_home(home) / "split_fingerprint_key"
