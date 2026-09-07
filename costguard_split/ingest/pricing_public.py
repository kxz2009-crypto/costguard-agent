"""P1A-09 optional public price estimation. DEFAULT OFF.

Opt-in via ``COSTGUARD_PUBLIC_PRICING`` in {1, true, TRUE}; every other
value (including unset) keeps ingestion completely unpriced. When enabled,
the CREATED ingest path may attach an informational
``api_equivalent_cost_usd`` computed with Decimal from the versioned
PUBLIC price table in ``costguard_split/data/public_pricing.json``.

Hard rules (spec section 9 / DoD 8):
- Decimal arithmetic only (``from decimal import Decimal, ROUND_HALF_UP``);
  binary floating point money is banned in the pricing path (N1 guards
  this file's source for the corresponding SQL type keywords too).
- Public table prices only; the result is an api-equivalent estimate and
  must never be presented as true internal cost.
- Missing price for a token class with tokens > 0 -> the whole estimate is
  NULL. Unknown model -> NULL. No partial pricing, ever.
- Duplicate/rejected ingests never recompute or mutate stored money.

Table note: ``reasoning_per_mtok`` is "0.0000" for providers whose
reasoning tokens are a subset of output_tokens (already billed via
output); a distinct reasoning price is only correct for providers that
bill reasoning separately.
"""

from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from os import environ
from pathlib import Path
from typing import Optional

from ..schemas.usage import UsageEventClaim

__all__ = ("FLAG_ENV", "public_pricing_enabled", "estimate_cost")

FLAG_ENV = "COSTGUARD_PUBLIC_PRICING"
_FLAG_TRUE = frozenset({"1", "true", "TRUE"})

_QUANTUM = Decimal("0.0001")
_PER_MTOK = Decimal(1000000)

_TABLE_PATH = Path(__file__).resolve().parents[1] / "data" / "public_pricing.json"

# claim token field -> table price field
_PRICE_FIELDS = (
    ("input_tokens", "input_per_mtok"),
    ("cached_input_tokens", "cache_read_per_mtok"),
    ("cache_write_tokens", "cache_write_per_mtok"),
    ("output_tokens", "output_per_mtok"),
    ("reasoning_tokens", "reasoning_per_mtok"),
)


def public_pricing_enabled() -> bool:
    """Feature flag: default OFF; exact opt-in values only."""
    return environ.get(FLAG_ENV, "") in _FLAG_TRUE


def _load_table(path: Path) -> tuple[str, dict]:
    """Parse and validate the public table. All prices MUST be decimal
    strings; any float literal or non-string price fails closed."""
    with open(path, encoding="utf-8") as handle:
        raw = json.load(handle, parse_float=_reject_float_literal)
    version = raw.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError("pricing table version must be a non-empty string")
    models: dict = {}
    for row in raw.get("models", ()):
        key = (row.get("provider"), row.get("model"))
        prices = {}
        for _, price_field in _PRICE_FIELDS:
            value = row.get(price_field)
            if value is None:
                continue
            if not isinstance(value, str):
                raise ValueError(
                    f"{key[0]}/{key[1]}: {price_field} must be a decimal "
                    "string, never a number")
            prices[price_field] = Decimal(value)
        models[key] = prices
    return version, models


def _reject_float_literal(text: str):
    raise ValueError(
        f"pricing table contains a float literal: {text!r} "
        "(decimal strings only)")


def estimate_cost(claim: UsageEventClaim,
                  table_path: Optional[Path] = None) -> tuple:
    """Return ``(pricing_version, api_equivalent_cost_usd)`` for a claim.

    ``(None, None)`` when: the flag is OFF, the model is unknown, a priced
    token class has tokens > 0 but no price, or the table is corrupted —
    estimation failures must never break ingestion (fail open to NULL),
    and must never produce a partial price (fail closed to NULL).
    """
    if not public_pricing_enabled():
        return None, None
    try:
        version, models = _load_table(
            Path(table_path) if table_path is not None else _TABLE_PATH)
        prices = models.get((claim.provider, claim.model))
        if prices is None:
            return None, None
        total = Decimal(0)
        for token_field, price_field in _PRICE_FIELDS:
            tokens = getattr(claim, token_field)
            price = prices.get(price_field)
            if tokens > 0:
                if price is None:
                    return None, None
                total += Decimal(tokens) * price
        cost = (total / _PER_MTOK).quantize(
            _QUANTUM, rounding=ROUND_HALF_UP)
        return version, str(cost)
    except Exception:
        return None, None
