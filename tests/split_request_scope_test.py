"""HTTP request transaction isolation for the shared SQLite connection."""
import asyncio
import threading
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from costguard_split.api.app import create_app
from costguard_split.api.context import ServerContext
from costguard_split.services import audit


def test_audit_failure_cannot_leak_into_next_request(tmp_path):
    app = create_app(tmp_path / 'test.db', ServerContext('synthetic-org'))
    with TestClient(app, raise_server_exceptions=False) as client:
        with patch.object(audit, 'record', side_effect=RuntimeError('synthetic audit failure')):
            assert client.post('/api/v1/members', json={'display_name':'must-rollback'}).status_code == 500
        assert client.post('/api/v1/members', json={'display_name':'valid'}).status_code == 201
        rows = client.get('/api/v1/members').json()
        assert [row['display_name'] for row in rows] == ['valid']
        member = rows[0]['member_id']
        with patch.object(audit, 'record', side_effect=RuntimeError('synthetic audit failure')):
            assert client.patch('/api/v1/members/' + member, json={'display_name':'bad-update'}).status_code == 500
        assert client.post('/api/v1/members', json={'display_name':'later'}).status_code == 201
        assert client.get('/api/v1/members/' + member).json()['display_name'] == 'valid'


def test_concurrent_requests_never_share_an_active_write(tmp_path):
    app = create_app(tmp_path / 'test.db', ServerContext('synthetic-org'))
    entered = threading.Event()
    release = threading.Event()
    entries = []
    original = audit.record
    def recording(*args, **kwargs):
        entries.append(kwargs['entity_id'])
        if len(entries) == 1:
            entered.set()
            assert release.wait(5)
        return original(*args, **kwargs)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            first = asyncio.create_task(client.post('/api/v1/members', json={'display_name':'first'}))
            second = None
            try:
                assert await asyncio.to_thread(entered.wait, 3)
                second = asyncio.create_task(client.post('/api/v1/members', json={'display_name':'second'}))
                await asyncio.sleep(.1)
                assert len(entries) == 1, 'second request entered the first transaction'
            finally:
                release.set()
                responses = await asyncio.gather(first, *([second] if second else []))
            assert all(r.status_code == 201 for r in responses)
            assert len((await client.get('/api/v1/members')).json()) == 2
    with patch.object(audit, 'record', side_effect=recording):
        asyncio.run(run())


def test_registration_audit_failure_is_rolled_back(tmp_path):
    path = tmp_path / 'test.db'
    app = create_app(path, ServerContext('synthetic-org'))
    payload = {'device_uid':'cgdev_00000000-0000-4000-8000-000000000001',
               'hostname_fingerprint':'hk1:' + 'a' * 32,
               'username_fingerprint':'hk1:' + 'b' * 32,
               'os':'synthetic', 'arch':'synthetic'}
    with TestClient(app, raise_server_exceptions=False) as client:
        with patch.object(audit, 'record', side_effect=RuntimeError('synthetic audit failure')):
            assert client.post('/api/v1/devices/register', json=payload).status_code == 500
        assert client.post('/api/v1/members', json={'display_name':'after-failure'}).status_code == 201
        import sqlite3
        with sqlite3.connect(path) as db:
            assert db.execute('SELECT COUNT(*) FROM devices').fetchone()[0] == 0
        assert client.post('/api/v1/devices/register', json=payload).status_code == 201
