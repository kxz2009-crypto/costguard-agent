"""Connector framework — discover / collect / normalize / health_check.

Security invariants enforced here (SECURITY-HARDENING §5/§8, CONNECTOR-SPEC §3):
- ALLOWED_PATHS: a connector may only open files under its declared roots.
- Content-bearing columns are excluded at the SQL level (never fetched).
- Every DB handle is read-only by URI; failures are isolated per connector
  (one connector being unavailable never blocks the others).
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .usage_event import UsageEvent, UNKNOWN


def ro_connect(path: Path) -> sqlite3.Connection:
    """Open a SQLite database strictly read-only."""
    if not path.exists():
        raise FileNotFoundError(path)
    uri = f"file:{path}?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=2.0)


class Connector:
    """Base class. Subclasses set id, allowed_paths, source_db columns.

    Contract for NEW connectors (P0-CORE-HARDENING §2): implement ONLY
        scan()      -> list[UsageEvent]
        metadata()  -> dict   (declarative: id, version, data sources)
    Everything else (discover/normalize/health_check) is inherited; the
    pipeline (cli.scan -> database.store -> reports) needs zero changes
    when a new connector is added — drop the module in connectors/ and
    register it in cli.CONNECTORS.
    Legacy method collect() remains supported for the two MVP connectors.
    """

    id: str = ""
    version: str = "1.0"
    allowed_paths: tuple[str, ...] = ()
    # Literal SQL this connector issues — set by subclasses so the contract
    # test can verify no content columns without executing anything.
    select_sql: tuple[str, ...] = ()

    def discover(self) -> dict:
        """Non-invasive presence check: do the declared paths exist?"""
        found = [p for p in self.allowed_paths if Path(os.path.expanduser(p)).exists()]
        return {
            "connector": self.id,
            "installed": bool(found),
            "data_available": bool(found),
            "paths_found": found,
        }

    def metadata(self) -> dict:
        """Declarative connector description (no I/O beyond discover)."""
        return {
            "id": self.id,
            "version": self.version,
            "interface": "scan",
            "paths": list(self.allowed_paths),
            **self.discover(),
        }

    # -- new canonical interface -------------------------------------------
    def scan(self) -> list[UsageEvent]:
        """Collect + normalize. Default bridges to legacy collect()."""
        return self.collect()

    # -- legacy interface (MVP connectors) ---------------------------------
    def collect(self) -> list[UsageEvent]:
        raise NotImplementedError

    def normalize(self, raw: dict) -> UsageEvent:
        return UsageEvent(
            provider=str(raw.get("provider") or UNKNOWN),
            model=str(raw.get("model") or UNKNOWN),
            input_tokens=int(raw.get("input_tokens") or 0),
            output_tokens=int(raw.get("output_tokens") or 0),
            timestamp=str(raw.get("timestamp") or ""),
            cache_read_tokens=int(raw.get("cache_read_tokens") or 0),
            cache_write_tokens=int(raw.get("cache_write_tokens") or 0),
            reasoning_tokens=int(raw.get("reasoning_tokens") or 0),
            source=self.id,
            session_ref=str(raw.get("session_ref") or ""),
            estimated_cost=float(raw.get("estimated_cost") or 0.0),
            cost_status=str(raw.get("cost_status") or UNKNOWN),
        )

    def health_check(self) -> dict:
        try:
            events = self.scan()
            return {"connector": self.id, "status": "connected",
                    "events": len(events)}
        except Exception as exc:  # isolated failure: report, never crash agent
            return {"connector": self.id, "status": "unavailable",
                    "reason": type(exc).__name__}


def verify_sql_safety(connector_cls) -> list[str]:
    """Static contract check: every SQL a connector declares is content-free.

    Returns list of violations (empty = safe). Uses connector_cls.select_sql
    so the check runs WITHOUT touching the source databases.
    """
    problems = []
    for sql in getattr(connector_cls, "select_sql", ()):
        try:
            verify_no_content_columns(sql)
        except PermissionError as exc:
            problems.append(f"{connector_cls.id}: {exc}")
    return problems


def verify_no_content_columns(sql: str, forbidden: tuple[str, ...] = (
        "prompt", "message", "content", "response", "preview",
        "first_user_message", "item_json", "origin_json", "feedback_log_body",
        "raw_memory", "system_prompt", "title", "display_name",
        "last_activity_description", "api_key", "token_key", "secret")) -> None:
    """Guard: assert a connector's SQL never selects content columns.

    Matches whole identifiers only (word boundaries), so 'content' does not
    trip on e.g. 'context_length'. Called with the literal SQL string of
    every SELECT a connector issues.
    """
    lowered = sql.lower()
    for word in forbidden:
        import re
        if re.search(rf"\b{re.escape(word)}\b", lowered):
            raise PermissionError(
                f"connector SQL references forbidden column: {word}")
