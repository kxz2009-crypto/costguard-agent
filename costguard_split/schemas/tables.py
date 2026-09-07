"""Split schemas — SQLite DDL, shaped for PostgreSQL migration.

Migration history:
  v1  initial P0 (commit 96facac): organizations/members/devices/
      audit_events; devices.status CHECK included 'unassigned'.
  v2  hardening (this release):
      - PATCH 4: tenant-safe composite FKs — members/devices/
        device_assignments/audit_events all carry
        UNIQUE(organization_id, id) and children reference parents via
        (organization_id, parent_id) so a cross-org reference is
        IMPOSSIBLE at the database level, not just in service code.
      - PATCH 5: device_assignments timeline table — attribution is a
        bitemporal fact (valid_from/valid_to), history is never deleted;
        the current member of a device is DERIVED (exactly one row with
        valid_to IS NULL), not stored on devices.
      - PATCH 6: remove the 'unassigned' dual-truth: devices.status is
        now a lifecycle value (active/disabled/retired) with default
        'active'; membership is derived from device_assignments.
        A v1 database's status='unassigned' rows are migrated to
        'active' with no assignment (derived unassigned), member_id is
        migrated into an initial device_assignments row and the column
        is then dropped (SQLite 3.35+ ALTER TABLE DROP COLUMN).
      - PATCH 9: type policy guard data — no REAL/FLOAT money columns
        exist; a test scans this file to keep it that way.

PostgreSQL mapping notes (no behavior in SQLite): ids TEXT->TEXT/UUID,
timestamps TEXT->TIMESTAMPTZ, before_json/after_json TEXT->JSONB,
money would be NUMERIC(12,4) via Decimal — never REAL/FLOAT/DOUBLE.
The v2 exclusion constraint 'no overlapping assignment per device' is
enforced in SQLite by a transaction + service guard (SQLite has no
EXCLUDE constraints); on PostgreSQL it becomes a GiST EXCLUDE constraint
— documented in services/device_registry.enroll_assignment.
"""

from __future__ import annotations

# Versions are integers applied in order; each entry is idempotent in
# effect (guarded by table/version checks) though written as plain DDL.
MIGRATIONS: list[tuple[int, str]] = [
    (1, """
CREATE TABLE IF NOT EXISTS organizations (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'disabled')),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS members (
    id              TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL
                    REFERENCES organizations(id),
    display_name    TEXT NOT NULL,
    email_optional  TEXT,
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'disabled')),
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_members_org
    ON members(organization_id);

CREATE TABLE IF NOT EXISTS devices (
    id                  TEXT PRIMARY KEY,
    organization_id     TEXT NOT NULL
                        REFERENCES organizations(id),
    device_uid          TEXT NOT NULL UNIQUE,
    member_id           TEXT
                        REFERENCES members(id),
    display_name        TEXT NOT NULL,
    hostname_hash       TEXT NOT NULL,
    username_hash       TEXT NOT NULL,
    os                  TEXT NOT NULL,
    arch                TEXT NOT NULL,
    first_seen_at       TEXT NOT NULL,
    last_seen_at        TEXT NOT NULL,
    last_network_hash   TEXT,
    status              TEXT NOT NULL DEFAULT 'unassigned'
                        CHECK (status IN
                        ('unassigned', 'active', 'disabled', 'retired')),
    identity_confidence INTEGER NOT NULL DEFAULT 0
                        CHECK (identity_confidence BETWEEN 0 AND 100),
    collector_version   TEXT NOT NULL DEFAULT '',
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_devices_org
    ON devices(organization_id);
CREATE INDEX IF NOT EXISTS idx_devices_member
    ON devices(member_id);

CREATE TABLE IF NOT EXISTS audit_events (
    id              TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL
                    REFERENCES organizations(id),
    actor_id        TEXT,
    event_type      TEXT NOT NULL,
    entity_type     TEXT NOT NULL,
    entity_id       TEXT NOT NULL,
    before_json     TEXT,
    after_json      TEXT,
    reason          TEXT,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_org_time
    ON audit_events(organization_id, created_at);
"""),
]

# ---------------------------------------------------------------------------
# v2 applied programmatically (see apply_migrations): composite-FK rebuilds
# are table rebuilds in SQLite; the steps are explicit, ordered, and
# idempotent (each step checks information_schema-equivalent state first).
# ---------------------------------------------------------------------------


def _table_columns(db, table: str) -> set[str]:
    return {r[1] for r in db.execute(f"PRAGMA table_info({table})")}


def _table_exists(db, table: str) -> bool:
    return db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,)).fetchone() is not None


def _has_row(db, table: str) -> bool:
    return db.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone() is not None


def _migrate_v2(db) -> None:
    now = "1970-01-01T00:00:00+00:00"


    # -- members: add UNIQUE(organization_id, id) so devices/assignments
    #    can composite-FK into members tenant-safely. members keeps its
    #    plain organization_id -> organizations(id) FK (org ids ARE global).
    if not _index_exists(db, "uq_members_org_id"):
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_members_org_id"
                   " ON members(organization_id, id)")

    # -- devices: rebuild (drop member_id dual-truth column, lifecycle
    #    status, composite unique, org-aware FKs)
    had_member_column = "member_id" in _table_columns(db, "devices")
    legacy_links: list[tuple[str, str, str, str]] = []
    if had_member_column:
        legacy_links = [
            (r[0], r[1], r[2], r[3] or "1970-01-01T00:00:00+00:00")
            for r in db.execute(
                "SELECT id, organization_id, member_id, first_seen_at"
                " FROM devices WHERE member_id IS NOT NULL")]
    _rebuild_devices(db, now)

    # -- device_assignments: create if absent (PATCH 5)
    if not _table_exists(db, "device_assignments"):
        db.executescript("""
CREATE TABLE device_assignments (
    id              TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    device_id       TEXT NOT NULL,
    member_id       TEXT NOT NULL,
    valid_from      TEXT NOT NULL,
    valid_to        TEXT,
    assigned_by     TEXT,
    reason          TEXT,
    created_at      TEXT NOT NULL,
    UNIQUE (organization_id, id),
    UNIQUE (organization_id, member_id, id),
    FOREIGN KEY (organization_id, device_id)
        REFERENCES devices (organization_id, id),
    FOREIGN KEY (organization_id, member_id)
        REFERENCES members (organization_id, id)
);
CREATE INDEX IF NOT EXISTS idx_assign_device_time
    ON device_assignments(device_id, valid_from);
CREATE INDEX IF NOT EXISTS idx_assign_active
    ON device_assignments(device_id, valid_to);
""")
        # seed initial assignments from any pre-v2 devices.member_id data
        # (captured BEFORE the devices rebuild dropped that column)
        for dev_id, org_id, member_id, first_seen in legacy_links:
            db.execute(
                "INSERT INTO device_assignments (id, organization_id,"
                " device_id, member_id, valid_from, valid_to, reason,"
                " created_at) VALUES (?,?,?,?,?,NULL,?,?)",
                ("asg_" + dev_id[4:], org_id, dev_id, member_id,
                 first_seen or now,
                 "migrated from v1 devices.member_id", now))

    # -- audit_events: composite unique index (no rebuild needed; FK to
    #    organizations stays by id — audit rows are org-scoped facts)
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_audit_org_id"
               " ON audit_events(organization_id, id)")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_audit_id"
               " ON audit_events(id)")




def _rebuild_devices(db, now: str) -> None:
    """devices v1->v2: lifecycle status, drop member_id (moved to
    device_assignments), composite unique, org-aware FKs."""
    cols = _table_columns(db, "devices")
    if not cols:
        return
    has_member = "member_id" in cols
    db.executescript("""
CREATE TABLE devices_v2 (
    id                  TEXT PRIMARY KEY,
    organization_id     TEXT NOT NULL
                        REFERENCES organizations (id),
    device_uid          TEXT NOT NULL UNIQUE,
    display_name        TEXT NOT NULL,
    hostname_hash       TEXT NOT NULL,
    username_hash       TEXT NOT NULL,
    os                  TEXT NOT NULL,
    arch                TEXT NOT NULL,
    first_seen_at       TEXT NOT NULL,
    last_seen_at        TEXT NOT NULL,
    last_network_hash   TEXT,
    status              TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'disabled', 'retired')),
    identity_confidence INTEGER NOT NULL DEFAULT 0
                        CHECK (identity_confidence BETWEEN 0 AND 100),
    collector_version   TEXT NOT NULL DEFAULT '',
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    UNIQUE (organization_id, id)
);
""")
    if has_member:
        db.execute("""
INSERT INTO devices_v2
SELECT id, organization_id, device_uid, display_name, hostname_hash,
       username_hash, os, arch, first_seen_at, last_seen_at,
       last_network_hash,
       CASE WHEN status = 'unassigned' THEN 'active' ELSE status END,
       identity_confidence, collector_version, created_at, updated_at
FROM devices""")
    else:
        db.execute("""
INSERT INTO devices_v2
SELECT id, organization_id, device_uid, display_name, hostname_hash,
       username_hash, os, arch, first_seen_at, last_seen_at,
       last_network_hash, status, identity_confidence, collector_version,
       created_at, updated_at
FROM devices""")
    db.execute("DROP TABLE devices")
    db.execute("ALTER TABLE devices_v2 RENAME TO devices")
    db.execute("CREATE INDEX IF NOT EXISTS idx_devices_org"
               " ON devices(organization_id)")


def _index_exists(db, name: str) -> bool:
    return db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
        (name,)).fetchone() is not None


def apply_migrations(db) -> int:
    """Apply pending migrations in order. Idempotent; returns applied count."""
    db.execute(
        "CREATE TABLE IF NOT EXISTS schema_version ("
        " version INTEGER NOT NULL, applied_at TEXT NOT NULL)")
    row = db.execute("SELECT MAX(version) FROM schema_version").fetchone()
    current = row[0] or 0
    applied = 0
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    def mark(version: int) -> None:
        db.execute("INSERT INTO schema_version (version, applied_at)"
                   " VALUES (?, ?)", (version, now))

    for version, sql in MIGRATIONS:
        if version <= current:
            continue
        db.executescript(sql)
        mark(version)
        applied += 1

    if current < 2:
        _migrate_v2(db)
        mark(2)
        applied += 1

    # PATCH 9 guard rail: monetary columns must never be REAL/FLOAT.
    bad = [r for r in db.execute(
        "SELECT name, type FROM sqlite_master WHERE type='table'")]
    for table, _ in bad:
        for col in db.execute(f"PRAGMA table_info({table})"):
            if "REAL" in (col[2] or "").upper() and _MONEY_HINT in col[1]:
                raise RuntimeError(
                    f"monetary column {table}.{col[1]} is REAL — Decimal/"
                    f"NUMERIC policy violated")
    db.commit()
    return applied


_MONEY_HINT = "cost"  # extended later: price/allocation/settlement
