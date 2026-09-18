"""Static and app-factory guards for the cloud-debug deployment bundle."""
import ast
import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "deploy" / "cloud-debug"
SPEC = importlib.util.spec_from_file_location(
    "costguard_cloud_debug_server", BUNDLE / "server.py"
)
assert SPEC is not None and SPEC.loader is not None
DEBUG_SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DEBUG_SERVER)

ACCEPTANCE_SPEC = importlib.util.spec_from_file_location(
    "costguard_cloud_debug_acceptance", BUNDLE / "acceptance.py"
)
assert ACCEPTANCE_SPEC is not None and ACCEPTANCE_SPEC.loader is not None
ACCEPTANCE = importlib.util.module_from_spec(ACCEPTANCE_SPEC)
ACCEPTANCE_SPEC.loader.exec_module(ACCEPTANCE)


def _text(name):
    return (BUNDLE / name).read_text()


def test_compose_is_single_process_loopback_only_and_persistent():
    compose = _text("compose.yaml")
    dockerfile = _text("Dockerfile")
    assert compose.count("  backend:") == 1
    assert "replicas:" not in compose
    assert "127.0.0.1:18080:8080" in compose
    assert "0.0.0.0:18080" not in compose
    assert "split_cloud_debug_data:/data" in compose
    assert "costguard_split_cloud_debug_data" in compose
    assert "restart: unless-stopped" in compose
    assert "internal: true" in compose
    assert "USER 10001:10001" in dockerfile
    assert "HEALTHCHECK" in dockerfile and "/healthz" in dockerfile
    assert 'CMD ["python", "/app/server.py"]' in dockerfile
    assert "COPY deploy/cloud-debug/server.py /app/server.py" in dockerfile
    assert "COPY deploy/cloud-debug/acceptance.py /app/acceptance.py" in dockerfile
    assert (BUNDLE / "acceptance.py").is_file()


def test_nginx_template_enforces_tls_auth_proxy_and_no_store():
    nginx = _text("nginx-costguardsplit.conf")
    assert "return 301 https://costguardsplit.nuxnow.com$request_uri;" in nginx
    assert "return 301 https://$host$request_uri;" not in nginx
    assert "listen 443 ssl;" in nginx and "http2 on;" in nginx
    assert "ssl_certificate     DEPLOY_TLS_CERTIFICATE_PATH;" in nginx
    assert "ssl_certificate_key DEPLOY_TLS_PRIVATE_KEY_PATH;" in nginx
    assert "auth_basic_user_file DEPLOY_HTPASSWD_PATH;" in nginx
    assert "proxy_pass http://127.0.0.1:18080;" in nginx
    assert 'proxy_set_header X-Forwarded-Proto https;' in nginx
    assert 'add_header Cache-Control "no-store" always;' in nginx
    assert "client_max_body_size 1m;" in nginx


def test_bundle_has_placeholders_not_secret_material():
    combined = "\n".join(
        path.read_text() for path in BUNDLE.iterdir() if path.is_file()
    )
    for marker in (
        "BEGIN PRIVATE KEY", "BEGIN CERTIFICATE", "password=", "passwd=",
        "API_KEY=", "SECRET=", "TOKEN=",
    ):
        assert marker not in combined
    assert "DEPLOY_HTPASSWD_PATH" in combined
    assert not list(BUNDLE.glob("*.db"))
    assert not list(BUNDLE.glob(".env*"))


def test_debug_factory_uses_overridable_synthetic_context(tmp_path, monkeypatch):
    db_path = tmp_path / "synthetic.db"
    monkeypatch.setenv("COSTGUARD_SPLIT_DB_PATH", str(db_path))
    monkeypatch.setenv("COSTGUARD_SPLIT_ORGANIZATION_ID", "org-test-override")
    monkeypatch.setenv("COSTGUARD_SPLIT_ACTOR_ID", "actor-test-override")
    with TestClient(DEBUG_SERVER.create_debug_app_from_env()) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        response = client.get("/api/v1/consumption/summary", params={
            "org_id": "foreign-test-org",
            "start": "2026-01-01T00:00:00Z",
            "end": "2026-01-02T00:00:00Z",
        })
        assert response.status_code == 404
        assert client.post(
            "/api/v1/members", json={"display_name": "synthetic-member"}
        ).json()["organization_id"] == "org-test-override"
    assert db_path.is_file()
    assert "synthetic" in DEBUG_SERVER.DEFAULT_ORGANIZATION_ID
    assert "synthetic" in DEBUG_SERVER.DEFAULT_ACTOR_ID


def test_debug_factory_rejects_blank_context(tmp_path, monkeypatch):
    monkeypatch.setenv("COSTGUARD_SPLIT_DB_PATH", str(tmp_path / "blank.db"))
    monkeypatch.setenv("COSTGUARD_SPLIT_ORGANIZATION_ID", " ")
    with pytest.raises(RuntimeError, match="must not be blank"):
        DEBUG_SERVER.create_debug_app_from_env()


def test_initial_acceptance_does_not_claim_or_run_restart_persistence():
    tree = ast.parse(_text("acceptance.py"))
    full = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "full_acceptance"
    )
    assert "restart persistence" not in {
        node.value for node in ast.walk(full)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert "restart_check" not in {
        node.func.id for node in ast.walk(full)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


def test_concurrent_accepted_members_are_read_back_by_id_and_name(monkeypatch):
    accepted = [
        {"member_id": "mem_synthetic_1", "display_name": "synthetic-1"},
        {"member_id": "mem_synthetic_2", "display_name": "synthetic-2"},
    ]
    monkeypatch.setattr(
        ACCEPTANCE,
        "request",
        lambda method, path, **kwargs: (200, accepted[:1]),
    )
    with pytest.raises(AssertionError):
        ACCEPTANCE.verify_concurrent_members(accepted)


def test_member_projection_is_complete_and_deterministic():
    members = [
        {"member_id": "mem_2", "display_name": "two", "status": "disabled"},
        {"member_id": "mem_1", "display_name": "one", "status": "active"},
    ]
    assert ACCEPTANCE.project_members(members) == [
        {"member_id": "mem_1", "display_name": "one", "status": "active"},
        {"member_id": "mem_2", "display_name": "two", "status": "disabled"},
    ]


def _valid_manifest(members=None, member_count=None, event_count=1):
    members = members or [{
        "member_id": "mem_synthetic",
        "display_name": "cloud-debug-concurrent-00",
        "status": "active",
    }]
    return {
        "schema_version": 1,
        "organization_id": ACCEPTANCE.ORG,
        "device": {
            "device_id": "dev_synthetic",
            "device_uid": ACCEPTANCE.UID,
            "status": "active",
            "assignment_status": "unassigned",
        },
        "event": {
            "id": "evt_synthetic",
            "source_event_id": f"synthetic-provider:{ACCEPTANCE.EVENT_ID}",
            "device_id": "dev_synthetic",
        },
        "members": members,
        "counts": {
            "members": len(members) if member_count is None else member_count,
            "events": event_count,
        },
    }


def _install_restart_state(tmp_path, monkeypatch, manifest, **overrides):
    manifest_path = tmp_path / "acceptance-expected.json"
    manifest_path.write_text(json.dumps(manifest))
    monkeypatch.setattr(ACCEPTANCE, "MANIFEST_PATH", manifest_path)
    responses = {
        "/api/v1/devices/dev_synthetic": (200, manifest["device"]),
        "/api/v1/usage/events/evt_synthetic": (200, manifest["event"]),
        "/api/v1/members": (200, manifest["members"]),
        "/api/v1/usage/events": (200, [manifest["event"]]),
    }
    responses.update(overrides)

    def request(method, path, payload=None, params=None):
        assert method == "GET"
        return responses[path]

    monkeypatch.setattr(ACCEPTANCE, "request", request)


def test_expected_manifest_is_written_atomically(tmp_path, monkeypatch):
    manifest_path = tmp_path / "acceptance-expected.json"
    monkeypatch.setattr(ACCEPTANCE, "MANIFEST_PATH", manifest_path)
    manifest = _valid_manifest()
    ACCEPTANCE.write_expected_manifest(manifest)
    assert json.loads(manifest_path.read_text()) == manifest
    assert not list(tmp_path.glob(".acceptance-expected.json.*"))


@pytest.mark.parametrize("contents", [None, "not-json", "{}"])
def test_restart_check_fails_closed_for_absent_or_corrupt_manifest(
    tmp_path, monkeypatch, contents
):
    manifest_path = tmp_path / "acceptance-expected.json"
    if contents is not None:
        manifest_path.write_text(contents)
    monkeypatch.setattr(ACCEPTANCE, "MANIFEST_PATH", manifest_path)
    with pytest.raises((AssertionError, ValueError, OSError, json.JSONDecodeError)):
        ACCEPTANCE.restart_check()


def test_restart_check_rejects_device_mismatch(tmp_path, monkeypatch):
    manifest = _valid_manifest()
    actual = {**manifest["device"], "status": "disabled"}
    _install_restart_state(
        tmp_path, monkeypatch, manifest,
        **{"/api/v1/devices/dev_synthetic": (200, actual)},
    )
    with pytest.raises(AssertionError, match="device state mismatch"):
        ACCEPTANCE.restart_check()


def test_restart_check_rejects_event_mismatch(tmp_path, monkeypatch):
    manifest = _valid_manifest()
    actual = {**manifest["event"], "device_id": "dev_other"}
    _install_restart_state(
        tmp_path, monkeypatch, manifest,
        **{"/api/v1/usage/events/evt_synthetic": (200, actual)},
    )
    with pytest.raises(AssertionError, match="event state mismatch"):
        ACCEPTANCE.restart_check()


def test_restart_check_rejects_missing_member(tmp_path, monkeypatch):
    members = [
        {"member_id": "mem_1", "display_name": "one", "status": "active"},
        {"member_id": "mem_2", "display_name": "two", "status": "active"},
    ]
    manifest = _valid_manifest(members)
    actual = [members[1], {
        "member_id": "mem_replacement",
        "display_name": "replacement",
        "status": "active",
    }]
    _install_restart_state(
        tmp_path, monkeypatch, manifest,
        **{"/api/v1/members": (200, actual)},
    )
    with pytest.raises(AssertionError, match="member state mismatch"):
        ACCEPTANCE.restart_check()


def test_restart_check_rejects_mutated_member_with_unchanged_count(
    tmp_path, monkeypatch
):
    manifest = _valid_manifest()
    mutated = [{**manifest["members"][0], "status": "disabled"}]
    _install_restart_state(
        tmp_path, monkeypatch, manifest,
        **{"/api/v1/members": (200, mutated)},
    )
    with pytest.raises(AssertionError, match="member state mismatch"):
        ACCEPTANCE.restart_check()


def test_restart_check_rejects_unexpected_extra_member(tmp_path, monkeypatch):
    members = [
        {"member_id": "mem_1", "display_name": "one", "status": "active"},
        {"member_id": "mem_2", "display_name": "two", "status": "active"},
    ]
    manifest = _valid_manifest(members)
    actual = [members[0], {
        "member_id": "mem_unexpected",
        "display_name": "unexpected",
        "status": "active",
    }]
    _install_restart_state(
        tmp_path, monkeypatch, manifest,
        **{"/api/v1/members": (200, actual)},
    )
    with pytest.raises(AssertionError, match="member state mismatch"):
        ACCEPTANCE.restart_check()


def test_restart_check_rejects_member_count_mismatch(tmp_path, monkeypatch):
    manifest = _valid_manifest()
    actual = manifest["members"] + [{
        "member_id": "mem_extra",
        "display_name": "extra",
        "status": "active",
    }]
    _install_restart_state(
        tmp_path, monkeypatch, manifest,
        **{"/api/v1/members": (200, actual)},
    )
    with pytest.raises(AssertionError, match="member count mismatch"):
        ACCEPTANCE.restart_check()


def test_restart_check_rejects_event_count_mismatch(tmp_path, monkeypatch):
    manifest = _valid_manifest()
    events = [manifest["event"], {**manifest["event"], "id": "evt_extra"}]
    _install_restart_state(
        tmp_path, monkeypatch, manifest,
        **{"/api/v1/usage/events": (200, events)},
    )
    with pytest.raises(AssertionError, match="event count mismatch"):
        ACCEPTANCE.restart_check()