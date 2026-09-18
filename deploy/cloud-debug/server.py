"""Narrow single-process entrypoint for the synthetic cloud-debug server.

This module does not add authentication. The deployment bundle terminates TLS
and requires HTTP Basic Auth at Nginx before proxying to this process.
"""
from __future__ import annotations

import os
from pathlib import Path

from costguard_split.api.app import create_app
from costguard_split.api.context import ServerContext

DEFAULT_DB_PATH = "/data/split.db"
DEFAULT_ORGANIZATION_ID = "org-cloud-debug-synthetic"
DEFAULT_ACTOR_ID = "actor-cloud-debug-synthetic"


def create_debug_app_from_env():
    """Create the explicitly synthetic, single-organization debug app."""
    db_path = Path(os.environ.get("COSTGUARD_SPLIT_DB_PATH", DEFAULT_DB_PATH))
    organization_id = os.environ.get(
        "COSTGUARD_SPLIT_ORGANIZATION_ID", DEFAULT_ORGANIZATION_ID
    ).strip()
    actor_id = os.environ.get(
        "COSTGUARD_SPLIT_ACTOR_ID", DEFAULT_ACTOR_ID
    ).strip()
    if not organization_id or not actor_id:
        raise RuntimeError("cloud-debug organization and actor IDs must not be blank")
    return create_app(
        db_path=db_path,
        context=ServerContext(organization_id=organization_id, actor_id=actor_id),
    )


def main() -> None:
    """Run one Uvicorn worker; RequestScope requires this exact topology."""
    import uvicorn

    uvicorn.run(
        create_debug_app_from_env(),
        host="0.0.0.0",
        port=8080,
        workers=1,
        access_log=False,
    )


if __name__ == "__main__":
    main()