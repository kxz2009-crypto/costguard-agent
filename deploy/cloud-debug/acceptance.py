#!/usr/bin/env python3
"""Synthetic runtime acceptance run inside the cloud-debug container."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import tempfile
import urllib.error
import urllib.parse
import urllib.request

from costguard_split.presentation.html_report import render_report_html
from costguard_split.report.dto import ReportDocument, ReportMeta

BASE = "http://127.0.0.1:8080"
ORG = os.environ.get(
    "COSTGUARD_SPLIT_ORGANIZATION_ID", "org-cloud-debug-synthetic"
)
UID = "cgdev_00000000-0000-4000-8000-000000000001"
EVENT_ID = "cloud-debug-synthetic-event-001"
MANIFEST_PATH = Path("/data/acceptance-expected.json")
MANIFEST_SCHEMA_VERSION = 1
CONCURRENT_MEMBER_COUNT = 8
MEMBER_MANIFEST_FIELDS = ("member_id", "display_name", "status")


def request(method, path, payload=None, params=None):
    if params:
        path += "?" + urllib.parse.urlencode(params)
    body = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        BASE + path,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return exc.code, json.loads(raw) if raw else None


def registration():
    return {
        "device_uid": UID,
        "hostname_fingerprint": "hk1:" + "a" * 32,
        "username_fingerprint": "hk1:" + "b" * 32,
        "network_fingerprint": "hk1:" + "c" * 32,
        "os": "synthetic",
        "arch": "synthetic",
        "collector_version": "cloud-debug-acceptance",
    }


def event():
    return {
        "device_uid": UID,
        "provider": "synthetic-provider",
        "source_event_id": EVENT_ID,
        "model": "synthetic-model",
        "started_at": "2026-09-10T00:00:00Z",
        "ended_at": "2026-09-10T00:01:00Z",
        "session_ref": "cloud-debug-synthetic-session",
        "input_tokens": 10,
        "output_tokens": 5,
        "request_count": 1,
        "collector_version": "cloud-debug-acceptance",
        "source_type": "manual",
    }


def verify_concurrent_members(accepted):
    """Read back every accepted concurrent member by both ID and name."""
    status, members = request("GET", "/api/v1/members")
    assert status == 200 and isinstance(members, list)
    actual = {(item["member_id"], item["display_name"]) for item in members}
    expected = {(item["member_id"], item["display_name"]) for item in accepted}
    assert len(expected) == len(accepted)
    assert expected <= actual
    return members


def project_members(members):
    """Project and deterministically order the complete member state."""
    return sorted(
        ({key: item[key] for key in MEMBER_MANIFEST_FIELDS} for item in members),
        key=lambda item: tuple(item[key] for key in MEMBER_MANIFEST_FIELDS),
    )


def write_expected_manifest(manifest):
    """Atomically persist synthetic expected state in the named volume."""
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{MANIFEST_PATH.name}.", dir=MANIFEST_PATH.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(manifest, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, MANIFEST_PATH)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def load_expected_manifest():
    with MANIFEST_PATH.open(encoding="utf-8") as stream:
        manifest = json.load(stream)
    assert isinstance(manifest, dict)
    assert set(manifest) == {
        "schema_version", "organization_id", "device", "event", "members", "counts"
    }
    assert manifest["schema_version"] == MANIFEST_SCHEMA_VERSION
    assert manifest["organization_id"] == ORG
    assert isinstance(manifest["device"], dict)
    assert set(manifest["device"]) == {
        "device_id", "device_uid", "status", "assignment_status"
    }
    assert manifest["device"]["device_uid"] == UID
    assert all(isinstance(value, str) and value for value in manifest["device"].values())
    assert isinstance(manifest["event"], dict)
    assert set(manifest["event"]) == {"id", "source_event_id", "device_id"}
    assert manifest["event"]["source_event_id"] == f"synthetic-provider:{EVENT_ID}"
    assert all(isinstance(value, str) and value for value in manifest["event"].values())
    assert isinstance(manifest["members"], list) and manifest["members"]
    for member in manifest["members"]:
        assert isinstance(member, dict)
        assert set(member) == set(MEMBER_MANIFEST_FIELDS)
        assert all(isinstance(value, str) and value for value in member.values())
    assert manifest["members"] == project_members(manifest["members"])
    assert isinstance(manifest["counts"], dict)
    assert set(manifest["counts"]) == {"members", "events"}
    assert all(
        isinstance(value, int) and not isinstance(value, bool) and value >= 0
        for value in manifest["counts"].values()
    )
    assert manifest["counts"]["members"] == len(manifest["members"])
    return manifest


def restart_check():
    """Fail closed unless all manifest-backed synthetic state still matches."""
    manifest = load_expected_manifest()

    expected_device = manifest["device"]
    status, device = request("GET", f"/api/v1/devices/{expected_device['device_id']}")
    assert status == 200 and isinstance(device, dict)
    assert {key: device[key] for key in expected_device} == expected_device, (
        "device state mismatch"
    )

    expected_event = manifest["event"]
    status, stored_event = request("GET", f"/api/v1/usage/events/{expected_event['id']}")
    assert status == 200 and isinstance(stored_event, dict)
    assert {key: stored_event[key] for key in expected_event} == expected_event, (
        "event state mismatch"
    )

    status, members = request("GET", "/api/v1/members")
    assert status == 200 and isinstance(members, list)
    assert len(members) == manifest["counts"]["members"], "member count mismatch"
    assert project_members(members) == manifest["members"], "member state mismatch"

    status, events = request("GET", "/api/v1/usage/events")
    assert status == 200 and isinstance(events, list)
    assert len(events) == manifest["counts"]["events"], "event count mismatch"
    assert sum(item["id"] == expected_event["id"] for item in events) == 1
    return [
        "manifest loaded",
        "device state persisted",
        "event state and count persisted",
        "member state and count persisted",
        "restart persistence",
    ]


def full_acceptance():
    checks = []
    status, body = request("GET", "/healthz")
    assert (status, body) == (200, {"status": "ok"})
    checks.append("health")

    status, _ = request("GET", "/api/v1/consumption/summary", params={
        "org_id": "foreign-synthetic-org",
        "start": "2026-09-01T00:00:00Z",
        "end": "2026-10-01T00:00:00Z",
    })
    assert status == 404
    checks.append("tenant guard")

    first_status, device = request("POST", "/api/v1/devices/register", registration())
    assert first_status in (200, 201)
    assert isinstance(device, dict)
    assert device["device_uid"] == UID
    checks.append("synthetic registration")

    created_status, created = request("POST", "/api/v1/usage/events", event())
    duplicate_status, duplicate = request("POST", "/api/v1/usage/events", event())
    assert created_status in (200, 201)
    assert duplicate_status == 200
    assert isinstance(created, dict) and isinstance(duplicate, dict)
    assert created["id"] == duplicate["id"]
    checks.extend(["ingestion", "deduplication"])

    params = {
        "org_id": ORG,
        "start": "2026-09-01T00:00:00Z",
        "end": "2026-10-01T00:00:00Z",
    }
    status, report = request(
        "GET", "/api/v1/consumption/report/summary", params=params
    )
    assert isinstance(report, dict)
    assert status == 200 and report["body"] and report["content_hash"]
    meta = report["meta"]
    document = ReportDocument(
        meta=ReportMeta(
            meta["schema_version"], meta["baseline"],
            meta["window"]["start"], meta["window"]["end"],
            meta["granularity"], meta["filters"]["provider"],
            meta["filters"]["model"], meta["filters"]["member_id"],
            meta["filters"]["device_id"],
        ),
        body=report["body"],
        content_hash=report["content_hash"],
    )
    html = render_report_html(document)
    assert html.startswith("<!doctype html>") and report["content_hash"] in html
    checks.extend(["report JSON", "installed HTML renderer"])

    def create_member(index):
        status, member = request("POST", "/api/v1/members", {
            "display_name": f"cloud-debug-concurrent-{index:02d}"
        })
        assert status == 201 and isinstance(member, dict)
        return member

    with ThreadPoolExecutor(max_workers=8) as pool:
        accepted_members = list(pool.map(create_member, range(CONCURRENT_MEMBER_COUNT)))
    all_members = verify_concurrent_members(accepted_members)
    checks.append("concurrent writes readback")

    status, stored_device = request("GET", f"/api/v1/devices/{device['device_id']}")
    assert status == 200 and isinstance(stored_device, dict)
    status, stored_event = request("GET", f"/api/v1/usage/events/{created['id']}")
    assert status == 200 and isinstance(stored_event, dict)
    status, all_events = request("GET", "/api/v1/usage/events")
    assert status == 200 and isinstance(all_events, list)
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "organization_id": ORG,
        "device": {
            key: stored_device[key]
            for key in ("device_id", "device_uid", "status", "assignment_status")
        },
        "event": {
            key: stored_event[key]
            for key in ("id", "source_event_id", "device_id")
        },
        "members": project_members(all_members),
        "counts": {"members": len(all_members), "events": len(all_events)},
    }
    write_expected_manifest(manifest)
    checks.append("expected state manifest written")
    return checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--restart-check", action="store_true")
    args = parser.parse_args()
    checks = restart_check() if args.restart_check else full_acceptance()
    print(json.dumps({"status": "PASS", "checks": checks}, sort_keys=True))


if __name__ == "__main__":
    main()
