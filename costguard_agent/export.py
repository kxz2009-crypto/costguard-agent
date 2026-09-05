"""Sync-preparation layer — export aggregated usage for future SaaS upload.

TASK P0-CORE-HARDENING §4: export ONLY. Nothing here performs network I/O;
the file it produces is the exact payload a future sync client would POST.

Privacy (hard boundary, verified by tests):
- Contents limited to: token counts, model, cost (with status), time.
- FORBIDDEN fields (prompt/response/content/keys) can never enter: the
  payload is built from the usage_fact whitelist projection, and a final
  self-scan rejects any forbidden key before writing.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from . import database
from .usage_event import SCHEMA_VERSION, UNKNOWN

EXPORT_DIR = Path(os.path.expanduser("~/.costguard/exports"))
FORBIDDEN_KEYS = ("prompt", "response", "content", "message", "secret",
                  "api_key", "token_key", "code", "text", "raw",
                  "filename", "path", "filepath", "file_path")

# Export schema v1 allowlist — the ONLY day-level keys permitted.
ALLOWED_DAY_KEYS = ("tokens", "events", "cost", "models")

# Whitelist projection from usage_fact — nothing else is selectable.
_AGG_SQL = """
SELECT event_date, provider, model, source,
       SUM(all_tokens)      AS tokens,
       SUM(estimated_cost)  AS cost_passthrough,
       SUM(CASE WHEN cost_status='estimated' THEN 1 ELSE 0 END)  AS priced_n,
       COUNT(*)             AS events
FROM usage_fact
WHERE event_date != 'unknown'
GROUP BY event_date, provider, model, source
ORDER BY event_date, tokens DESC
"""


def build_export_payload() -> dict:
    """Aggregate usage_fact -> SaaS-ready payload (no raw events, no ids).

    Schema v1 (Task 3): day -> models -> {provider -> sources -> tokens}.
    `provider` is a first-class dimension; UNKNOWN providers are preserved
    verbatim (never guessed).
    """
    db = database.connect()
    try:
        rows = db.execute(_AGG_SQL).fetchall()
    finally:
        db.close()
    daily: dict[str, dict] = {}
    for (day, provider, model, source, tokens, cost, priced_n,
         events) in rows:
        d = daily.setdefault(day, {"tokens": 0, "events": 0,
                                   "cost": {"estimated": 0.0,
                                            "unknown_passthrough": 0.0},
                                   "models": {}})
        d["tokens"] += tokens
        d["events"] += events
        if priced_n:
            d["cost"]["estimated"] += cost
        else:
            d["cost"]["unknown_passthrough"] += cost
        m = d["models"].setdefault(model, {"tokens": 0, "events": 0,
                                           "providers": {}})
        m["tokens"] += tokens
        m["events"] += events
        pv = m["providers"].setdefault(provider, {
            "token_count": 0, "events": 0, "sources": {}})
        pv["token_count"] += tokens
        pv["events"] += events
        pv["sources"][source] = pv["sources"].get(source, 0) + tokens
    # round costs after summing
    for d in daily.values():
        d["cost"]["estimated"] = round(d["cost"]["estimated"], 8)
        d["cost"]["unknown_passthrough"] = round(
            d["cost"]["unknown_passthrough"], 8)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "exported_at": datetime.now(tz=timezone.utc).isoformat(),
        "granularity": "daily_model_provider_source",
        "days": len(daily),
        "usage": {day: {
            "tokens": v["tokens"],
            "events": v["events"],
            "cost": v["cost"],
            "models": {
                model: {
                    "tokens": m["tokens"],
                    "events": m["events"],
                    "providers": {
                        provider: {
                            "token_count": pv["token_count"],
                            "events": pv["events"],
                            "sources": pv["sources"],
                        } for provider, pv in m["providers"].items()
                    },
                } for model, m in v["models"].items()
            },
        } for day, v in sorted(daily.items())},
    }
    # structural allowlist check: every day object carries exactly the
    # permitted keys (whitelist, not blacklist).
    for day_obj in payload["usage"].values():
        unexpected = set(day_obj) - set(ALLOWED_DAY_KEYS)
        if unexpected:
            raise ValueError(f"export day object has unexpected keys: "
                             f"{sorted(unexpected)}")
    return payload


def assert_no_forbidden_payload(payload: dict) -> None:
    """Recursively reject forbidden keys anywhere in the payload."""
    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                kl = str(k).lower()
                for word in FORBIDDEN_KEYS:
                    if kl == word or kl.endswith("_" + word):
                        raise PermissionError(
                            f"export payload contains forbidden key: {k}")
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)
    walk(payload)


def export(path: str | None = None) -> Path:
    """Write aggregated_usage.json (0600). Returns the file path."""
    payload = build_export_payload()
    assert_no_forbidden_payload(payload)          # hard gate before write
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = Path(path) if path else EXPORT_DIR / "aggregated_usage.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    os.chmod(out, 0o600)
    return out
