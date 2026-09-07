"""P1A-07 usage HTTP route tests.

Real FastAPI TestClient against the real ingest service (no ingest mocks).
Each test owns a temp SQLite DB shared by two app instances (two org
contexts) so tenant isolation is exercised through the HTTP layer only.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from fastapi.testclient import TestClient
    _DEPS = True
except ImportError:                                  # pragma: no cover
    _DEPS = False

from costguard_split import db as split_db
from costguard_split.api.app import create_app
from costguard_split.api.context import ServerContext

UID = "cgdev_018f0c9a-1605-4bec-8000-17b71faba7e1"
UID2 = "cgdev_018f0c9a-1605-4bec-8000-17b71faba7e2"
ORG = "org-test"
ORG_OTHER = "org-test-2"

T1 = "2026-09-10T00:00:00+00:00"
T2 = "2026-09-10T00:05:00+00:00"


def claim_payload(**overrides):
    payload = {
        "device_uid": UID,
        "provider": "claude",
        "source_event_id": "msg_01ABC",
        "model": "claude-sonnet-4-5",
        "started_at": T1,
        "ended_at": T2,
        "session_ref": "11111111-2222-3333-4444-555555555555",
        "input_tokens": 100,
        "cached_input_tokens": 2000,
        "cache_write_tokens": 40,
        "output_tokens": 300,
        "reasoning_tokens": 0,
        "request_count": 1,
        "collector_version": "2.0.14",
        "source_type": "connector",
    }
    payload.update(overrides)
    return payload


@unittest.skipUnless(_DEPS, "fastapi/httpx not installed ([split-server])")
class UsageApiTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "split.db"
        self.ctx = ServerContext(organization_id=ORG)
        self._seed_orgs()
        self.client = TestClient(
            create_app(db_path=self.db_path, context=self.ctx),
            raise_server_exceptions=False)
        self.client_other = TestClient(create_app(
            db_path=self.db_path,
            context=ServerContext(organization_id=ORG_OTHER)),
            raise_server_exceptions=False)
        # org-a device
        self.assertEqual(
            self.client.post("/api/v1/devices/register", json={
                "device_uid": UID,
                "hostname_fingerprint": "hk1:" + "a" * 32,
                "username_fingerprint": "hk1:" + "c" * 32,
                "os": "Linux", "arch": "x86_64"}).status_code, 201)
        # org-b device (same uid shape, different org)
        self.assertEqual(
            self.client_other.post("/api/v1/devices/register", json={
                "device_uid": UID2,
                "hostname_fingerprint": "hk1:" + "b" * 32,
                "username_fingerprint": "hk1:" + "d" * 32,
                "os": "Linux", "arch": "x86_64"}).status_code, 201)

    def tearDown(self):
        self._tmp.cleanup()

    def _seed_orgs(self):
        db = split_db.connect(path=self.db_path)
        for org in (ORG, ORG_OTHER):
            db.execute(
                "INSERT INTO organizations (id, name, status, created_at,"
                " updated_at) VALUES (?, 'Test Org', 'active', 't', 't')",
                (org,))
        db.commit()
        db.close()

    def _audits(self):
        db = split_db.connect(path=self.db_path)
        rows = db.execute(
            "SELECT event_type FROM audit_events "
            "WHERE event_type LIKE 'usage.%' ORDER BY rowid").fetchall()
        db.close()
        return [row[0] for row in rows]

    def post_event(self, payload=None, client=None):
        return (client or self.client).post(
            "/api/v1/usage/events", json=payload or claim_payload())


class SingleEventTests(UsageApiTestBase):
    def test_created_returns_201_and_event_shape(self):
        response = self.post_event()
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertTrue(body["id"].startswith("uev_"))
        self.assertEqual(body["organization_id"], ORG)
        self.assertEqual(body["provider"], "claude")
        self.assertIsNone(body["member_id"])
        self.assertIsNone(body["pricing_version"])
        self.assertIsNone(body["api_equivalent_cost_usd"])
        self.assertEqual(self._audits(), ["usage.ingested"])

    def test_duplicate_replay_returns_200_same_id(self):
        first = self.post_event()
        second = self.post_event()
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["id"], first.json()["id"])
        self.assertEqual(self._audits(),
                         ["usage.ingested", "usage.duplicate"])

    def test_unknown_device_is_404_hidden_without_usage_write(self):
        response = self.post_event(claim_payload(device_uid=UID2))
        self.assertEqual(response.status_code, 404)
        db = split_db.connect(path=self.db_path)
        count = db.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0]
        db.close()
        self.assertEqual(count, 0)
        self.assertEqual(self._audits(), ["usage.rejected"])

    def test_conflict_returns_409(self):
        self.post_event()
        conflict = self.post_event(
            claim_payload(output_tokens=999, source_event_id="msg_01ABC"))
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["detail"]["error"],
                         "usage_conflict")

    def test_forbidden_and_server_fields_are_422(self):
        base = claim_payload()
        for field in ("organization_id", "member_id", "device_id",
                      "received_at", "created_at", "pricing_version",
                      "api_equivalent_cost_usd", "hostname", "prompt",
                      "response", "raw_ip"):
            response = self.post_event({**base, field: "spoof"})
            self.assertEqual(response.status_code, 422, msg=field)
        self.assertEqual(self._audits(), [])

    def test_float_and_bool_tokens_are_422(self):
        for bad in (1.5, True):
            response = self.post_event(
                claim_payload(input_tokens=bad))
            self.assertEqual(response.status_code, 422, msg=repr(bad))

    def test_naive_timestamp_is_422(self):
        response = self.post_event(claim_payload(started_at="2026-09-10T00:00:00"))
        self.assertEqual(response.status_code, 422)


class BatchTests(UsageApiTestBase):
    def post_batch(self, envelope, client=None):
        return (client or self.client).post(
            "/api/v1/usage/events:batch", json=envelope)

    def test_mixed_results_partial_success(self):
        accepted = claim_payload(source_event_id="msg_01")
        accepted_again = claim_payload(source_event_id="msg_01")
        unknown_device = claim_payload(source_event_id="msg_02",
                                       device_uid=UID2)
        conflicting = claim_payload(source_event_id="msg_03")
        response = self.post_batch({"events": [
            accepted, unknown_device, accepted_again, conflicting]})
        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertEqual([r["status"] for r in results],
                         ["created", "rejected", "duplicate", "created"])
        # accepted siblings survive the rejected item
        self.assertNotEqual(results[0]["event_id"], results[3]["event_id"])
        self.assertIsNone(results[1]["event_id"])
        self.assertEqual(
            self._audits(),
            ["usage.ingested", "usage.rejected", "usage.duplicate",
             "usage.ingested"])

    def test_over_500_items_is_422_with_zero_writes(self):
        events = [claim_payload(source_event_id=f"m{i}")
                  for i in range(501)]
        response = self.post_batch({"events": events})
        self.assertEqual(response.status_code, 422)
        db = split_db.connect(path=self.db_path)
        count = db.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0]
        db.close()
        self.assertEqual(count, 0)

    def test_malformed_json_is_422_with_zero_writes(self):
        response = self.client.post(
            "/api/v1/usage/events:batch",
            content=b"{not json",
            headers={"content-type": "application/json"})
        self.assertEqual(response.status_code, 422)
        db = split_db.connect(path=self.db_path)
        count = db.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0]
        db.close()
        self.assertEqual(count, 0)

    def test_oversize_body_is_413(self):
        # One claim whose session_ref alone pushes the JSON past 1 MiB.
        blob = json.dumps({
            "events": [claim_payload(
                session_ref="x" * (1024 * 1024 + 100))]}).encode()
        self.assertGreater(len(blob), 1024 * 1024)
        response = self.client.post(
            "/api/v1/usage/events:batch", content=blob,
            headers={"content-type": "application/json"})
        self.assertEqual(response.status_code, 413)

    def test_forbidden_top_level_keys_are_422(self):
        response = self.post_batch({
            "events": [claim_payload()], "organization_id": "spoof"})
        self.assertEqual(response.status_code, 422)

    def test_empty_batch_is_200_empty(self):
        response = self.post_batch({"events": []})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"], [])


class ReadEventTests(UsageApiTestBase):
    def test_get_by_id_for_own_org(self):
        created = self.post_event().json()
        response = self.client.get(f"/api/v1/usage/events/{created['id']}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], created["id"])

    def test_get_foreign_event_is_404_hidden(self):
        created = self.post_event().json()
        response = self.client_other.get(
            f"/api/v1/usage/events/{created['id']}")
        self.assertEqual(response.status_code, 404)

    def test_get_unknown_id_is_404(self):
        response = self.client.get("/api/v1/usage/events/uev_nope")
        self.assertEqual(response.status_code, 404)

    def test_list_filters_and_org_scope(self):
        self.post_event(claim_payload(source_event_id="m1"))
        self.post_event(claim_payload(
            source_event_id="m2", provider="codex",
            started_at="2026-09-11T00:00:00+00:00",
            ended_at="2026-09-11T00:05:00+00:00"))
        # other org's data must not leak into this list
        self.assertEqual(self.client_other.get(
            "/api/v1/usage/events").json(), [])

        everything = self.client.get("/api/v1/usage/events").json()
        self.assertEqual(len(everything), 2)
        by_provider = self.client.get(
            "/api/v1/usage/events", params={"provider": "CODEX"}).json()
        self.assertEqual([e["source_event_id"] for e in by_provider],
                         ["codex:m2"])
        by_window = self.client.get(
            "/api/v1/usage/events", params={"from": "2026-09-11T00:00:00Z"}
        ).json()
        self.assertEqual([e["source_event_id"] for e in by_window],
                         ["codex:m2"])
        empty_window = self.client.get(
            "/api/v1/usage/events", params={"to": "2026-09-09T00:00:00Z"}
        ).json()
        self.assertEqual(empty_window, [])

    def test_list_invalid_filter_is_400(self):
        response = self.client.get(
            "/api/v1/usage/events", params={"from": "yesterday"})
        self.assertEqual(response.status_code, 400)


class AssignmentAttributionTests(UsageApiTestBase):
    def test_member_at_is_derived_through_api_path(self):
        member = self.client.post(
            "/api/v1/members", json={"display_name": "Alice"}).json()
        # Assignments address devices by internal id; fetch it directly
        # from the DB (read-only fixture setup, not part of the route
        # contract under test).
        db = split_db.connect(path=self.db_path)
        device_id = db.execute(
            "SELECT id FROM devices WHERE device_uid = ?", (UID,)
        ).fetchone()[0]
        db.close()
        assign = self.client.post(
            f"/api/v1/devices/{device_id}/assignments",
            json={"member_id": member["member_id"],
                  "valid_from": "2026-09-01T00:00:00+00:00"})
        self.assertEqual(assign.status_code, 201)
        body = self.post_event().json()
        self.assertEqual(body["member_id"], member["member_id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
