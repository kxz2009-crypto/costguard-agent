"""CostGuard Split P0-04/05/06 API tests (T24-T60).

Layer under test: costguard_split/api (FastAPI adapter + services).
Run: python -m unittest tests.split_api_test -v
Isolation: every test builds its own tmp DB via create_app(db_path=...);
no real ~/.costguard is touched. Fixtures are obviously fake
(org-test, test-member, TEST-NET-3 IPs). Tests skip cleanly when the
optional [split-server] extra (fastapi/httpx) is absent so the core
wheel's contract tests stay framework-independent.
"""

from __future__ import annotations

import os
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
HK1 = "hk1:" + "a" * 32
HK2 = "hk1:" + "b" * 32
ORG = "org-test"
ORG_OTHER = "org-test-2"

EVIDENCE = {
    "device_uid": UID,
    "hostname_fingerprint": HK1,
    "username_fingerprint": HK2,
    "os": "Linux",
    "arch": "x86_64",
}


@unittest.skipUnless(_DEPS, "fastapi/httpx not installed ([split-server])")
class ApiTestBase(unittest.TestCase):
    """One app per test, own tmp DB, own org context."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "split.db"
        self.ctx = ServerContext(organization_id=ORG)
        self._seed_orgs()
        self.client = TestClient(create_app(db_path=self.db_path,
                                            context=self.ctx),
                                 raise_server_exceptions=False)
        self.client_other = TestClient(create_app(
            db_path=self.db_path,
            context=ServerContext(organization_id=ORG_OTHER)),
            raise_server_exceptions=False)

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

    # -- helpers ----------------------------------------------------------
    def register(self, client=None, uid=UID, **overrides):
        payload = dict(EVIDENCE, device_uid=uid, **overrides)
        return (client or self.client).post("/api/v1/devices/register",
                                            json=payload)

    def create_member(self, client=None, name="test-member",
                      email=None):
        return (client or self.client).post(
            "/api/v1/members",
            json={"display_name": name, "email_optional": email})


class DeviceRegistrationTests(ApiTestBase):
    """P0-04 — spec test list 1..15."""

    def test_01_new_device_register(self):
        r = self.register()
        self.assertEqual(r.status_code, 201)
        body = r.json()
        self.assertEqual(body["device_uid"], UID)
        self.assertEqual(body["status"], "active")
        self.assertEqual(body["assignment_status"], "unassigned")
        self.assertTrue(body["first_seen_at"])
        self.assertTrue(body["last_seen_at"])

    def test_02_repeated_register_idempotent(self):
        first = self.register()
        again = self.register()
        self.assertEqual(first.status_code, 201)
        self.assertEqual(again.status_code, 200)      # idempotent, not 201
        self.assertEqual(first.json()["device_id"],
                         again.json()["device_id"])
        self.assertEqual(first.json()["first_seen_at"],
                         again.json()["first_seen_at"])

    def test_03_last_seen_server_update(self):
        first = self.register().json()
        again = self.register(
            network_fingerprint="hk1:" + "c" * 32).json()
        self.assertGreaterEqual(again["last_seen_at"],
                                first["last_seen_at"])

    def test_04_unknown_device_has_no_assignment(self):
        body = self.register().json()
        self.assertEqual(body["assignment_status"], "unassigned")
        # derived: no assignment row exists for this device
        db = split_db.connect(path=self.db_path)
        n = db.execute(
            "SELECT COUNT(*) FROM device_assignments WHERE device_id = ?",
            (body["device_id"],)).fetchone()[0]
        db.close()
        self.assertEqual(n, 0)

    def test_05_client_member_id_rejected(self):
        r = self.register(member_id="mem_inject")
        self.assertEqual(r.status_code, 422)
        db = split_db.connect(path=self.db_path)
        n = db.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
        db.close()
        self.assertEqual(n, 0)                        # nothing persisted

    def test_06_client_organization_id_rejected(self):
        r = self.register(organization_id="org-inject")
        self.assertEqual(r.status_code, 422)
        # organization of the device is ALWAYS the server context org
        self.register()
        db = split_db.connect(path=self.db_path)
        orgs = [r[0] for r in db.execute(
            "SELECT DISTINCT organization_id FROM devices")]
        db.close()
        self.assertEqual(orgs, [ORG])

    def test_07_client_cost_field_rejected(self):
        r = self.register(api_equivalent_cost=999999)
        self.assertEqual(r.status_code, 422)

    def test_08_raw_hostname_rejected(self):
        r = self.register(hostname="real-host")
        self.assertEqual(r.status_code, 422)

    def test_09_raw_username_rejected(self):
        r = self.register(username="admin")
        self.assertEqual(r.status_code, 422)

    def test_10_raw_ip_rejected(self):
        r = self.register(ip="1.2.3.4")
        self.assertEqual(r.status_code, 422)
        r = self.register(raw_ip="1.2.3.4")
        self.assertEqual(r.status_code, 422)

    def test_11_malformed_device_uid_rejected(self):
        for bad in ("cg-nope", "cgdev_NOT-A-UUID",
                    "cgdev_018f0c9a-1605-4bec-8000-17b71faba7zz"):
            r = self.register(uid=bad)
            self.assertIn(r.status_code, (400, 422), bad)

    def test_12_malformed_fingerprint_rejected(self):
        r = self.register(hostname_fingerprint="real-host")
        self.assertIn(r.status_code, (400, 422))
        r = self.register(username_fingerprint="hk1:short")
        self.assertIn(r.status_code, (400, 422))

    def test_13_cross_org_same_device_uid_conflict_409(self):
        self.register()                                    # org-test owns UID
        r = self.register(client=self.client_other)        # org-test-2 wants it
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["error"], "device_uid_conflict")
        # security audit written
        db = split_db.connect(path=self.db_path)
        types = [x[0] for x in db.execute(
            "SELECT event_type FROM audit_events WHERE organization_id = ?",
            (ORG_OTHER,))]
        db.close()
        self.assertIn("device.registration_rejected", types)

    def test_14_device_response_no_secret_or_raw_evidence(self):
        r = self.register()
        body = r.json()
        forbidden = ("hostname", "username", "ip", "fingerprint", "hk1:",
                     "key", "secret", "member", "organization_id")
        for f in forbidden:
            self.assertNotIn(f, body)

    def test_15_tenant_isolation_on_device_get(self):
        body = self.register().json()
        # other org cannot see the device even with the exact id
        r = self.client_other.get(f"/api/v1/devices/{body['device_id']}")
        self.assertEqual(r.status_code, 404)

    def test_malicious_spoof_payload_rejected_atomically(self):
        """Spec attack payload: every forbidden claim in one request."""
        evil = dict(EVIDENCE, organization_id="other-org",
                    member_id="mem_target", identity_confidence=100,
                    api_equivalent_cost=999999,
                    hostname="real-host", username="admin", ip="1.2.3.4")
        r = self.register(**{k: v for k, v in evil.items()
                             if k not in EVIDENCE})
        self.assertEqual(r.status_code, 422)
        db = split_db.connect(path=self.db_path)
        n = db.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
        db.close()
        self.assertEqual(n, 0)                        # nothing persisted


class MemberCrudTests(ApiTestBase):
    """P0-05 — spec test list 1..10."""

    def test_01_create_member(self):
        r = self.create_member(email="someone@example.com")
        self.assertEqual(r.status_code, 201)
        body = r.json()
        self.assertEqual(body["display_name"], "test-member")
        self.assertEqual(body["status"], "active")
        self.assertTrue(body["member_id"].startswith("mem_"))

    def test_02_list_members_scoped(self):
        self.create_member(name="test-member-1")
        self.create_member(name="test-member-2")
        other = self.create_member(client=self.client_other,
                                   name="outsider")
        self.assertEqual(other.status_code, 201)
        names = [m["display_name"]
                 for m in self.client.get("/api/v1/members").json()]
        self.assertEqual(names, ["test-member-1", "test-member-2"])

    def test_03_get_member(self):
        mid = self.create_member().json()["member_id"]
        r = self.client.get(f"/api/v1/members/{mid}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["member_id"], mid)

    def test_04_update_display_name(self):
        mid = self.create_member().json()["member_id"]
        r = self.client.patch(f"/api/v1/members/{mid}",
                              json={"display_name": "renamed-member"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["display_name"], "renamed-member")

    def test_05_disable_member(self):
        mid = self.create_member().json()["member_id"]
        r = self.client.patch(f"/api/v1/members/{mid}",
                              json={"status": "disabled"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "disabled")

    def test_06_invalid_member_input(self):
        r = self.create_member(name="")
        self.assertEqual(r.status_code, 422)
        r = self.create_member(email="not-an-email")
        self.assertEqual(r.status_code, 422)
        r = self.client.post("/api/v1/members", json={"bogus": 1})
        self.assertEqual(r.status_code, 422)

    def test_07_org_a_cannot_read_org_b_member(self):
        foreign = self.create_member(client=self.client_other)
        self.assertEqual(foreign.status_code, 201)
        fid = foreign.json()["member_id"]
        r = self.client.get(f"/api/v1/members/{fid}")     # exact known id
        self.assertEqual(r.status_code, 404)              # hidden, not 403

    def test_08_org_a_cannot_update_org_b_member(self):
        fid = self.create_member(client=self.client_other).json()["member_id"]
        r = self.client.patch(f"/api/v1/members/{fid}",
                              json={"display_name": "hijacked"})
        self.assertEqual(r.status_code, 404)
        # untouched
        still = self.client_other.get(f"/api/v1/members/{fid}").json()
        self.assertEqual(still["display_name"], "test-member")

    def test_09_disabled_member_state_preserved(self):
        mid = self.create_member().json()["member_id"]
        self.client.patch(f"/api/v1/members/{mid}",
                          json={"status": "disabled"})
        # more CRUD happens afterwards; state must survive
        self.create_member(name="test-member-2")
        r = self.client.get(f"/api/v1/members/{mid}")
        self.assertEqual(r.json()["status"], "disabled")

    def test_10_no_hard_delete_path(self):
        from fastapi.routing import APIRoute
        delete_routes = [rt for rt in self.client.app.routes
                         if isinstance(rt, APIRoute)
                         and "DELETE" in rt.methods]
        self.assertEqual(delete_routes, [])   # no DELETE endpoint at all
        # and no hard-delete function in the member service
        from costguard_split.api import members as member_api
        for banned in ("delete_member", "remove_member", "hard_delete"):
            self.assertFalse(hasattr(member_api, banned))


if __name__ == "__main__":
    unittest.main(verbosity=2)
