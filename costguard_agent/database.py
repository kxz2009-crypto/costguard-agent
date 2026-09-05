"""SQLite storage layer — ~/.costguard/costguard.db (0600).

Two tables per CG-DATA-SCHEMA-001 (MVP subset):
- raw_usage_event: verbatim connector output (source of truth, re-playable)
- usage_fact: normalized facts powering all reports (cost_event deferred:
  the collector never prices; pricing_registry arrives in a later phase)

The source DBs are never written; -wal/-shm side files cannot appear on
them because we open read-only and never enable WAL here.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .usage_event import UsageEvent

CG_DIR = Path(os.path.expanduser("~/.costguard"))
DB_PATH = CG_DIR / "costguard.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_usage_event (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    provider TEXT,
    model TEXT,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    cache_read_tokens INTEGER DEFAULT 0,
    cache_write_tokens INTEGER DEFAULT 0,
    reasoning_tokens INTEGER DEFAULT 0,
    timestamp TEXT,
    session_ref TEXT,
    estimated_cost REAL DEFAULT 0.0,
    cost_status TEXT DEFAULT 'unknown',
    collected_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS usage_fact (
    id INTEGER PRIMARY KEY,
    source TEXT,
    provider TEXT,
    model TEXT,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    all_tokens INTEGER DEFAULT 0,
    timestamp TEXT,
    event_date TEXT,
    estimated_cost REAL DEFAULT 0.0,
    cost_status TEXT DEFAULT 'unknown',
    raw_id INTEGER REFERENCES raw_usage_event(id)
);
CREATE INDEX IF NOT EXISTS idx_fact_date ON usage_fact(event_date);
CREATE INDEX IF NOT EXISTS idx_fact_model ON usage_fact(model);
"""


def connect() -> sqlite3.Connection:
    """Open (creating if needed) the local CostGuard DB with 0600 perms."""
    CG_DIR.mkdir(parents=True, exist_ok=True)
    if not DB_PATH.exists():
        DB_PATH.touch(mode=0o600)
    os.chmod(DB_PATH, 0o600)  # enforce even if it pre-existed
    db = sqlite3.connect(DB_PATH)
    db.executescript(_SCHEMA)
    return db


def store(events: list[UsageEvent]) -> tuple[int, int]:
    """Insert events; dedupe by (source, session_ref, timestamp). Returns
    (rows_inserted, rows_seen). Idempotent — safe to re-run scan."""
    db = connect()
    try:
        seen = inserted = 0
        for ev in events:
            seen += 1
            row = ev.to_row()
            cur = db.execute(
                "SELECT 1 FROM raw_usage_event WHERE source=? AND session_ref=?"
                " AND timestamp=? LIMIT 1",
                (row["source"], row["session_ref"], row["timestamp"]))
            if cur.fetchone():
                continue
            ts_day = row["timestamp"][:10] if row["timestamp"] else "unknown"
            db.execute(
                "INSERT INTO raw_usage_event (source, provider, model,"
                " input_tokens, output_tokens, total_tokens,"
                " cache_read_tokens, cache_write_tokens, reasoning_tokens,"
                " timestamp, session_ref, estimated_cost, cost_status,"
                " collected_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?, datetime('now'))",
                (row["source"], row["provider"], row["model"],
                 row["input_tokens"], row["output_tokens"], row["total_tokens"],
                 row["cache_read_tokens"], row["cache_write_tokens"],
                 row["reasoning_tokens"], row["timestamp"], row["session_ref"],
                 row["estimated_cost"], row["cost_status"]))
            rid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            db.execute(
                "INSERT INTO usage_fact (source, provider, model,"
                " input_tokens, output_tokens, total_tokens, all_tokens,"
                " timestamp, event_date, estimated_cost, cost_status, raw_id)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (row["source"], row["provider"], row["model"],
                 row["input_tokens"], row["output_tokens"], row["total_tokens"],
                 ev.all_tokens, row["timestamp"], ts_day,
                 row["estimated_cost"], row["cost_status"], rid))
            inserted += 1
        db.commit()
        return inserted, seen
    finally:
        db.close()
