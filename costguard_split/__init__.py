"""CostGuard Split — AI Subscription Cost Allocation & Internal Chargeback.

Split P0 scope (spec v0.1 §29): identity domain only.
  costguard_split/
    __init__.py      this file — version + package boundary
    db.py            split-local SQLite (separate file, same data dir)
    identity/
      __init__.py
      device.py      persistent device_uid (cgdev_*) + evidence + confidence
      fingerprints.py keyed HMAC fingerprints (hostname/username/network)
    models/
      __init__.py
      entities.py    Organization / Member / Device / AuditEvent dataclasses
    schemas/
      __init__.py
      tables.py      DDL (SQLite dialect, PostgreSQL-migratable shapes)
    services/
      __init__.py
      device_registry.py  upsert device rows; unknown => unassigned
      audit.py            append-only audit_events writer

Hard boundaries (P0):
- NO network I/O, NO payments, NO allocation/settlement, NO UI.
- Unknown devices are NEVER auto-attributed: member_id stays NULL,
  status stays 'unassigned'.
- Raw hostname/username/IP never persisted — keyed fingerprints only.

Reuse (not duplication) from costguard_agent:
- storage location convention (database.CG_DIR, resolved dynamically),
- 0600 file-permission discipline,
- plain-stdlib testing style.
"""

from __future__ import annotations

__version__ = "0.1.0-p0"
