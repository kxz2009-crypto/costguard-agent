"""Pricing registry — local, offline, versioned price table (Free Beta).

Design:
- The table ships INSIDE the package (costguard_agent/data/pricing.json):
  zero network requests, ever. Refresh happens by package update only.
- lookup() never invents prices: an unknown model returns UNPRICED, and the
  report layer must show it as unknown — never as $0 (a $0 display would
  read as "free", which is a lie we refuse to tell).
- Amounts derived from this table are ESTIMATES: the report layer prefixes
  them with "~" and stamps price_table_version alongside.
- Zero-input-price entries (local/free models) are legitimate: priced=True
  with price 0. That is different from UNPRICED (unknown).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from typing import Optional

UNPRICED = None  # sentinel for "model not in table" — never 0.0


@dataclass(frozen=True)
class Price:
    canonical: str
    input_per_mtok: float
    output_per_mtok: float
    currency: str


class PriceTable:
    def __init__(self, table: dict):
        self.table_version: str = table["table_version"]
        self.currency: str = table.get("currency", "USD")
        self._by_alias: dict[str, Price] = {}
        for entry in table["models"]:
            p = Price(entry["canonical"], float(entry["input"]),
                      float(entry["output"]), self.currency)
            for alias in entry.get("aliases", [entry["canonical"]]):
                self._by_alias[alias] = p

    @classmethod
    def load_builtin(cls) -> "PriceTable":
        raw = resources.files("costguard_agent.data").joinpath(
            "pricing.json").read_text(encoding="utf-8")
        return cls(json.loads(raw))

    def lookup(self, raw_model: str) -> Optional[Price]:
        """Exact alias/canonical match. Case-insensitive; whitespace-stripped.
        Returns None (UNPRICED) for unknown models — caller must render
        'unknown', never '$0'."""
        if not raw_model:
            return None
        return self._by_alias.get(raw_model.strip().lower())

    def normalize(self, raw_model: str) -> str:
        """Canonical name if known; otherwise the raw name verbatim
        (unknown models are NEVER renamed or guessed)."""
        p = self.lookup(raw_model)
        return p.canonical if p else (raw_model or "UNKNOWN")

    @property
    def known_aliases(self) -> int:
        return len(self._by_alias)


def cost_usd(price: Price, input_tokens: int, output_tokens: int) -> float:
    """Estimate cost for a token split. Round to 8dp to match store precision."""
    return round((input_tokens * price.input_per_mtok
                  + output_tokens * price.output_per_mtok) / 1_000_000, 8)
