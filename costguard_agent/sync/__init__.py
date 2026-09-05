"""Sync layer — export JSON -> Cloud Ingest DTO. Payload ONLY, never sends.

Boundary (SaaS Integration Preparation, this phase):
- NO network I/O anywhere in this package. There is intentionally no
  sync client: the DTO produced here is what a future client would POST.
- The adapter is pure: dict-in -> dict-out. No hidden state.

Cloud Ingest DTO contract (v1):
{
  "schema_version": 1,
  "device": {"device_id": "cg-<32 hex>", "agent_version": "0.1.0"},
  "sync":    {"created_at": ISO, "mode": "manual",
              "dry_run": bool, "enabled": false},
  "records": [{date, provider, model, token_count, cost_status,
               estimated_cost, source, events}, ...]
}
- records granularity: one row per (date, provider, model, source).
- FORBIDDEN fields impossible by construction: the DTO is built only from
  the export whitelist projection, and assert_no_forbidden_payload() runs
  again on the final DTO before it is returned/written.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .. import __version__ as AGENT_VERSION
from ..export import (EXPORT_DIR, assert_no_forbidden_payload,
                      build_export_payload)

DEFAULT_DTO_PATH = EXPORT_DIR / "cloud_ingest_dto.json"

# Flat-record allowlist — the ONLY keys a record may carry.
RECORD_FIELDS = ("date", "provider", "model", "token_count", "cost_status",
                 "estimated_cost", "source", "events")

# Cloud Sync switch. Default OFF; nothing in this phase can enable it.
SYNC_DEFAULT_ENABLED = False


def _day_cost_fields(day_data: dict) -> tuple[str, float]:
    """Day-level cost -> (status, estimated_amount), honest and coarse.

    The export carries day-level cost buckets, not per-record cost. A day
    counts as 'estimated' only if estimated > 0 AND unknown_passthrough == 0;
    otherwise 'unknown'. Values are never invented.
    """
    cost = day_data.get("cost", {})
    est = round(float(cost.get("estimated", 0.0)), 8)
    unk = round(float(cost.get("unknown_passthrough", 0.0)), 8)
    if est > 0 and unk == 0.0:
        return "estimated", est
    return "unknown", est


def build_records(export_payload: dict) -> list[dict]:
    """Flatten export payload -> one record per (date, provider, model, source).

    Export schema v1 carries provider as a first-class dimension
    (day -> models -> providers -> {token_count, events, sources}).
    Per-record cost is day-level (coarse but honest): status is
    'estimated' only when the day's estimated bucket > 0 and its
    unknown_passthrough == 0; otherwise 'unknown'. Never invented.
    """
    records: list[dict] = []
    for day, day_data in export_payload.get("usage", {}).items():
        status, est = _day_cost_fields(day_data)
        for model, m in day_data.get("models", {}).items():
            for provider, pv in m.get("providers", {}).items():
                records.append({
                    "date": day,
                    "provider": provider,
                    "model": model,
                    "token_count": int(pv.get("token_count", 0)),
                    "cost_status": status,
                    "estimated_cost": est,
                    "source": _sole_source(pv),
                    "events": int(pv.get("events", 0)),
                })
    return records


def _sole_source(pv: dict) -> str:
    """Return the single source id when there is exactly one, else the
    token-major source with a '+N' suffix (aggregation is honest; nothing
    fabricated). Keeps records flat without hiding multi-source rows."""
    sources = pv.get("sources", {})
    if not sources:
        return "UNKNOWN"
    if len(sources) == 1:
        return next(iter(sources))
    major = max(sources.items(), key=lambda kv: kv[1])[0]
    return f"{major}+{len(sources) - 1}"


def to_ingest_dto(export_payload: dict,
                  device_id: str,
                  created_at: str | None = None,
                  mode: str = "manual",
                  dry_run: bool = True) -> dict:
    """export payload -> Cloud Ingest DTO (pure; no I/O)."""
    dto = {
        "schema_version": export_payload.get("schema_version", 1),
        "device": {"device_id": device_id, "agent_version": AGENT_VERSION},
        "sync": {
            "created_at": created_at or datetime.now(tz=timezone.utc).isoformat(),
            "mode": mode,
            "dry_run": bool(dry_run),
            "enabled": SYNC_DEFAULT_ENABLED,
        },
        "records": build_records(export_payload),
    }
    assert_no_forbidden_payload(dto)   # same hard gate as export
    return dto


def write_dto(dto: dict, path: str | None = None) -> Path:
    """Persist the DTO locally (0600). Still NO network I/O."""
    out = Path(path) if path else DEFAULT_DTO_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dto, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    os.chmod(out, 0o600)
    return out


def load_export(path: Path | None = None) -> dict:
    """Read a previously exported aggregated_usage.json from disk."""
    src = Path(path) if path else EXPORT_DIR / "aggregated_usage.json"
    return json.loads(src.read_text(encoding="utf-8"))


def status() -> dict:
    """Introspection for CLI/tests: what would sync do? (It does nothing.)"""
    return {
        "enabled": SYNC_DEFAULT_ENABLED,
        "transport": None,
        "note": "sync client not implemented in this phase; "
                "to_ingest_dto/write_dto only",
    }
