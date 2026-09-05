"""UsageEvent — the unified usage record produced by every connector.

Field contract (CG-CONNECTOR-SPEC-001 §6, narrowed by MVP reality):
- provider / model / timestamp are metadata (allowed).
- input_tokens / output_tokens: split when the source provides it.
- total_tokens is ALWAYS input+output as stored here; sources that only
  expose a cumulative counter (e.g. Codex threads.tokens_used) keep
  input_tokens=0 and put the counter in output_tokens — the split is
  UNKNOWN, never guessed. cost_status follows the same rule: UNKNOWN is
  preserved, never fabricated.
- token_fields() is the single source of truth for "what counts as a
  token" so every aggregation layer uses the same 5 fields.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

UNKNOWN = "UNKNOWN"

# Canonical cost_status vocabulary (contract, lowercase):
#   "estimated" — a price was computed/attached by the SOURCE
#   "unknown"   — no reliable price; any cost value is pass-through only
# The loud legacy constant UNKNOWN ("UNKNOWN", uppercase) is kept for
# backwards compatibility; normalize maps both None and legacy values to
# the canonical "unknown".
COST_ESTIMATED = "estimated"
COST_UNKNOWN = "unknown"
VALID_COST_STATUS = (COST_ESTIMATED, COST_UNKNOWN)

# --- Stable interface contract (SaaS-ingestion ready) -----------------------
# SCHEMA_VERSION bumps ONLY on breaking field changes; consumers (future SaaS
# API) pin against this. Fields below are the public contract; everything else
# in UsageEvent is additive and optional for consumers.
SCHEMA_VERSION = 1

# Required fields every connector MUST produce (non-empty / usable).
REQUIRED_FIELDS = ("provider", "model", "timestamp", "source")

# Token fields summed into a report's token total (single source of truth).
TOKEN_FIELDS = ("input_tokens", "output_tokens", "cache_read_tokens",
                "cache_write_tokens", "reasoning_tokens")

# The machine-readable projection of an event — exactly what /report --json
# and export emit per event. Additive fields are appended only in minor
# versions; removals/renames require SCHEMA_VERSION bump.
CONTRACT_FIELDS = ("source", "provider", "model",
                   "input_tokens", "output_tokens", "total_tokens",
                   "cache_read_tokens", "cache_write_tokens",
                   "reasoning_tokens", "all_tokens",
                   "timestamp", "estimated_cost", "cost_status")


def _iso(ts: float | int | None) -> str:
    """Epoch seconds -> ISO-8601 UTC string; None -> empty (never guessed)."""
    if ts is None:
        return ""
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()


@dataclass
class UsageEvent:
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    timestamp: str = ""          # ISO-8601 UTC
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    source: str = ""             # connector id: "hermes" | "codex" | ...
    session_ref: str = ""        # source-local reference (id may be sensitive upstream)
    estimated_cost: float = 0.0  # pass-through from source; collector never prices
    cost_status: str = COST_UNKNOWN  # "estimated" | "unknown" — preserved

    def __post_init__(self) -> None:
        # Canonicalize legacy/None values into the contract vocabulary.
        # (None / "UNKNOWN" / "Unknown" -> "unknown"; never fabricates.)
        if not self.cost_status or str(self.cost_status).lower() != COST_ESTIMATED:
            self.cost_status = COST_UNKNOWN
        else:
            self.cost_status = COST_ESTIMATED

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def all_tokens(self) -> int:
        """total + cache + reasoning — the dedup-safe sum used for stats."""
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
            + self.reasoning_tokens
        )

    def to_row(self) -> dict:
        return {
            "source": self.source,
            "provider": self.provider,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "timestamp": self.timestamp,
            "session_ref": self.session_ref,
            "estimated_cost": self.estimated_cost,
            "cost_status": self.cost_status,
        }

    def to_contract(self) -> dict:
        """Stable machine-readable projection (CONTRACT_FIELDS, in order).

        Excludes session_ref (source-local id — not part of the public
        contract; privacy) — this is the shape SaaS ingestion will see.
        """
        row = self.to_row()
        row["all_tokens"] = self.all_tokens
        return {k: row[k] for k in CONTRACT_FIELDS}

    def validate(self) -> list[str]:
        """Contract self-check. Returns list of violations (empty = valid)."""
        problems = []
        for f in REQUIRED_FIELDS:
            if not str(getattr(self, f) or "").strip():
                problems.append(f"missing required field: {f}")
        for f in TOKEN_FIELDS:
            v = getattr(self, f)
            if not isinstance(v, int) or v < 0:
                problems.append(f"invalid {f}: {v!r} (must be non-negative int)")
        if self.cost_status not in VALID_COST_STATUS:
            problems.append(f"invalid cost_status: {self.cost_status!r}")
        return problems


# Backwards-compatible alias (older imports).
token_fields = TOKEN_FIELDS


def token_sum(row: dict) -> int:
    return sum(int(row.get(k) or 0) for k in TOKEN_FIELDS)
