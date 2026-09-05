"""Device Identity — local anonymous ID. No account, no OAuth, no login.

Design (SaaS Integration Preparation, Task 2):
- The ID is generated once, on first run, and stored locally in
  ~/.costguard/device_id (0600).
- Format: "cg-" + 32 lowercase hex chars (128-bit random, secrets module).
- It is NOT derived from hardware, MAC, username, hostname, or any PII —
  it is pure randomness, so it cannot be correlated with the owner.
- It is NOT an account: it identifies THIS device's data stream only.
  Losing the file simply mintes a new identity (data would then look like
  a new device server-side — acceptable, and honest).
- get_or_create() is the only accessor; everything else in the codebase
  receives the id as a plain string parameter.
"""

from __future__ import annotations

import os
import re
import secrets
from pathlib import Path

from .database import CG_DIR

DEVICE_ID_FILE = CG_DIR / "device_id"
_ID_PATTERN = re.compile(r"^cg-[0-9a-f]{32}$")


def new_device_id() -> str:
    return "cg-" + secrets.token_hex(16)


def is_valid(device_id: str) -> bool:
    return bool(_ID_PATTERN.match(device_id or ""))


def get_or_create(path: Path | None = None) -> str:
    """Return the stored device id, creating it on first run."""
    f = Path(path) if path else DEVICE_ID_FILE
    f.parent.mkdir(parents=True, exist_ok=True)
    if f.exists():
        did = f.read_text(encoding="utf-8").strip()
        if is_valid(did):
            return did
        # corrupt/foreign content: replace, don't trust
    did = new_device_id()
    f.write_text(did + "\n", encoding="utf-8")
    os.chmod(f, 0o600)
    return did
