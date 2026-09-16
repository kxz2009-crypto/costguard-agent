"""Request ownership for the API factory's single SQLite connection.

Complete HTTP requests are serialized, including batch and exception paths.
Domain services keep their existing commit points. Any unfinished transaction
is discarded before the next request can enter. One app/process owns this
connection; direct service callers still own their own transaction discipline.
"""
from __future__ import annotations

import asyncio


class RequestScope:
    def __init__(self, app, db):
        self.app = app
        self.db = db
        self.lock = asyncio.Lock()

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        async with self.lock:
            try:
                await self.app(scope, receive, send)
            finally:
                # Covers handled HTTP errors and unexpected exceptions alike.
                # Never commit residual data left by an unsuccessful mutation.
                if self.db.in_transaction:
                    self.db.rollback()
