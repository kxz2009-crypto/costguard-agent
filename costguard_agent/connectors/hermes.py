"""Hermes Connector (P0) — reads ~/.hermes/state.db session_model_usage.

Verified against live schema (2026-09-04, PRAGMA):
  session_model_usage(session_id, model, billing_provider, ..., input_tokens,
  output_tokens, cache_read_tokens, cache_write_tokens, reasoning_tokens,
  estimated_cost_usd, cost_status, first_seen REAL epoch-s, last_seen)

Rules honored (COSTGUARD_AGENT_CONTEXT_LOCAL.md):
- Read-only URI + no side files -> cannot create -wal/-shm on source.
- cost_status is passed through verbatim (estimated | unknown | NULL->unknown).
- Provider is billing_provider verbatim; empty -> UNKNOWN, never guessed.
- Single layer: per-model-usage rows are the token source of truth (the
  sessions table carries overlapping aggregates; summing both would 2x).
"""

from __future__ import annotations

import os
from pathlib import Path

from ..connector_base import Connector, ro_connect, verify_no_content_columns
from ..usage_event import UNKNOWN, _iso

DB_PATH = "~/.hermes/state.db"

# Whitelisted metadata columns ONLY. No title/system_prompt/origin_json/etc.
_SELECT = """
SELECT session_id, model, billing_provider,
       input_tokens, output_tokens,
       cache_read_tokens, cache_write_tokens, reasoning_tokens,
       estimated_cost_usd, cost_status, last_seen
FROM session_model_usage
"""


class HermesConnector(Connector):
    id = "hermes"
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
        for (sid, model, provider, it, ot, cr, cw, rz,
             cost, status, seen) in rows:
            events.append(self.normalize({
                "provider": provider or UNKNOWN,
                "model": model or UNKNOWN,
                "input_tokens": it or 0,
                "output_tokens": ot or 0,
                "cache_read_tokens": cr or 0,
                "cache_write_tokens": cw or 0,
                "reasoning_tokens": rz or 0,
                "timestamp": _iso(seen),
                "session_ref": sid or "",
                "estimated_cost": float(cost or 0.0),
                "cost_status": status or UNKNOWN,
            }))
        return events
