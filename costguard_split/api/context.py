"""P0-04/05/06 server context abstraction + tenant guard.

There is no real auth system in P0 (and none may be silently invented).
Every API call receives an explicit ServerContext naming the organization
the request acts on and the actor performing it. Production servers will
derive this from authenticated transport; tests construct it directly.
Core rule: organization membership ALWAYS comes from this context —
never from a client JSON body.
"""

from __future__ import annotations

from dataclasses import dataclass

SYSTEM_ACTOR = "system"          # explicit test/system actor; NOT a real
                                 # user identity and never rendered as one


@dataclass(frozen=True)
class ServerContext:
    """The server-side authority for one API request."""
    organization_id: str
    actor_id: str = SYSTEM_ACTOR


class TenantViolation(LookupError):
    """A referenced resource does not belong to the caller's organization.

    Subclasses LookupError so the API layer maps it to 404 (resource
    hidden — no tenant enumeration). Never leak whether a foreign-id
    resource exists.
    """


def assert_tenant(db, table: str, *, organization_id: str,
                  row_id: str, id_column: str = "id") -> str:
    """Tenant-boundary gate: the row must exist inside THIS organization.

    Implemented as the single choke point every service read/mutation goes
    through; combined with the composite (organization_id, id) DB
    constraints this is defense in depth (service + database).
    """
    row = db.execute(
        f"SELECT id FROM {table} WHERE id = ? AND organization_id = ?",
        (row_id, organization_id)).fetchone()
    if row is None:
        raise TenantViolation(f"{table[:-1] if table.endswith('s') else table}"
                              f" not found")
    return row[0]
