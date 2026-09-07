"""Compatibility bridge to the CostGuard Agent core (reuse, no duplication).

Imported lazily so the Split package can degrade gracefully if the agent
package is absent (future standalone packaging), while P0 lives in-repo and
always resolves it.
"""

from __future__ import annotations

import importlib
import sys


def agent_database():
    """Return the costguard_agent.database module (call-time resolution)."""
    mod = sys.modules.get("costguard_agent.database")
    if mod is not None:
        return mod
    return importlib.import_module("costguard_agent.database")
