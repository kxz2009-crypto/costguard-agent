"""Codex Connector (P0) — reads ~/.codex/sqlite/state_5.sqlite threads table.

Verified against live schema (2026-09-04, PRAGMA):
  threads(id, model, model_provider, tokens_used, created_at_ms,
  updated_at_ms, source, ...)

Reality constraints (recorded honestly):
- tokens_used is a CUMULATIVE counter with no input/output split.
  => input_tokens stays 0, output_tokens carries the counter; the split
  is UNKNOWN and is never fabricated (per contract).
- model is NULL for older rows -> recorded as UNKNOWN, never guessed.
- CONTENT COLUMNS ARE NEVER SELECTED: first_user_message, preview,
  item_json (thread_history DB), title, etc. This connector reads ONLY
  the state DB and only the columns named below.
"""

from __future__ import annotations

import os
from pathlib import Path

from ..connector_base import Connector, ro_connect, verify_no_content_columns
from ..usage_event import UNKNOWN, _iso

DB_PATH = "~/.codex/sqlite/state_5.sqlite"

# Metadata-only whitelist. Guarded by verify_no_content_columns at runtime.
_SELECT = """
SELECT id, model, model_provider, tokens_used, updated_at_ms
FROM threads
WHERE tokens_used IS NOT NULL AND tokens_used > 0
"""


class CodexConnector(Connector):
    id = "codex"
    version = "1.0"
    allowed_paths = (DB_PATH,)
    select_sql = (_SELECT,)

    def collect(self) -> list:
        root = Path(os.path.expanduser(DB_PATH))
        sql = _SELECT
        verify_no_content_columns(sql)
        db = ro_connect(root)
        try:
            rows = db.execute(sql).fetchall()
        finally:
            db.close()
        events = []
        for (tid, model, provider, used, updated_ms) in rows:
            events.append(self.normalize({
                "provider": provider or UNKNOWN,
                "model": model or UNKNOWN,          # NULL -> UNKNOWN, no guessing
                "input_tokens": 0,                   # split unavailable in source
                "output_tokens": int(used),          # cumulative counter verbatim
                "timestamp": _iso(int(updated_ms) / 1000.0 if updated_ms else None),
                "session_ref": tid or "",
                "estimated_cost": 0.0,
                "cost_status": UNKNOWN,              # no pricing info in source
            }))
        return events
