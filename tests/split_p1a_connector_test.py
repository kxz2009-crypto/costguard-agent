"""P1A-04 connector framework tests.

Covers the BaseConnector contract, the explicit provider registry, the
connector trust boundary (no server-owned fields, no pricing/ingest/P1B
imports or symbols) and one integration flow proving a connector claim
reaches UsageEvent only through the ingest service.
"""

from __future__ import annotations

import ast
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from costguard_split import db as split_db
from costguard_split.api.context import ServerContext, TenantViolation
from costguard_split.connectors import (
    BaseConnector,
    ConnectorRegistry,
    DuplicateProviderError,
    InvalidProviderNameError,
    RawUsage,
    UnknownProviderError,
)
from costguard_split.ingest.service import ingest_usage_event
from costguard_split.models.usage import UsageEvent
from costguard_split.schemas.usage import SERVER_OWNED_FIELDS, UsageEventClaim

T1 = "2026-09-10T00:00:00+00:00"
T2 = "2026-09-20T00:00:00+00:00"
UID_A = "cgdev_018f0c9a-1605-4bec-8000-17b71faba7e1"
UID_B = "cgdev_018f0c9a-1605-4bec-8000-17b71faba7e2"
CONNECTORS_DIR = (
    Path(__file__).resolve().parents[1] / "costguard_split" / "connectors")

# Import roots that must never appear in any connector module: server-side
# layers (ingest/pricing/models/api) and anything network-capable.
_FORBIDDEN_IMPORT_ROOTS = frozenset((
    "ingest", "pricing", "models", "api",
    "urllib", "socket", "ssl", "http", "httpx", "requests", "subprocess",
))
# P1B capability vocabulary that must not appear as any code identifier.
_FORBIDDEN_SYMBOL_TOKENS = (
    "attribution", "lineage", "confidence", "quota", "recommendation",
    "pricing", "cost", "money",
)


class StubConnector(BaseConnector):
    name = "stub"

    def discover(self, home, since=None):
        yield RawUsage(payload={
            "model": "stub-model",
            "started_at": T1,
            "ended_at": T2,
            "native_id": "native-stub-1",
        })

    def normalize(self, raw):
        payload = raw.payload
        return UsageEventClaim(
            device_uid=self.device_uid,
            provider=self.name,
            source_event_id=self.native_event_id(raw),
            model=payload["model"],
            started_at=datetime.fromisoformat(payload["started_at"]),
            ended_at=datetime.fromisoformat(payload["ended_at"]),
            session_ref="stub-session",
            input_tokens=10,
            output_tokens=20,
            collector_version="stub-1.0",
            source_type="connector",
        )

    def native_event_id(self, raw):
        return raw.payload.get("native_id")


class IncompleteConnector(BaseConnector):
    name = "incomplete"

    def discover(self, home, since=None):
        return iter(())


def _import_segments(tree):
    segments = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                segments.update(alias.name.split("."))
        elif isinstance(node, ast.ImportFrom):
            segments.update((node.module or "").split("."))
    return segments


def _code_identifiers(tree):
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            names.add(node.name.lower())
        elif isinstance(node, ast.Name):
            names.add(node.id.lower())
        elif isinstance(node, ast.Attribute):
            names.add(node.attr.lower())
        elif isinstance(node, ast.keyword) and node.arg:
            names.add(node.arg.lower())
    return names


class BaseConnectorContractTests(unittest.TestCase):
    def test_abstract_base_cannot_be_instantiated(self):
        with self.assertRaises(TypeError):
            BaseConnector(device_uid=UID_A)

    def test_incomplete_implementation_cannot_be_instantiated(self):
        with self.assertRaises(TypeError):
            IncompleteConnector(device_uid=UID_A)

    def test_device_uid_must_be_canonical_and_is_injected(self):
        with self.assertRaises(ValueError):
            StubConnector(device_uid="hostname-guess")
        connector = StubConnector(device_uid=UID_A)
        self.assertEqual(connector.device_uid, UID_A)

    def test_raw_usage_is_frozen_including_payload(self):
        raw = RawUsage(payload={"model": "m"})
        with self.assertRaises(FrozenInstanceError):
            raw.payload = {}
        with self.assertRaises(TypeError):
            raw.payload["model"] = "other"

    def test_normalize_returns_plain_usage_event_claim(self):
        connector = StubConnector(device_uid=UID_A)
        raw = next(connector.discover(Path(tempfile.gettempdir())))
        claim = connector.normalize(raw)
        self.assertIs(type(claim), UsageEventClaim)
        self.assertEqual(claim.device_uid, UID_A)
        self.assertEqual(claim.source_event_id, "native-stub-1")

    def test_native_event_id_may_be_absent(self):
        connector = StubConnector(device_uid=UID_A)
        anonymous = RawUsage(payload={
            "model": "stub-model", "started_at": T1, "ended_at": T2})
        self.assertIsNone(connector.native_event_id(anonymous))


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = ConnectorRegistry()

    def test_register_and_get_roundtrip(self):
        self.registry.register("stub", StubConnector)
        self.assertIs(self.registry.get("stub"), StubConnector)
        self.assertEqual(self.registry.providers(), ("stub",))

    def test_duplicate_registration_rejected(self):
        self.registry.register("stub", StubConnector)
        with self.assertRaises(DuplicateProviderError):
            self.registry.register("stub", StubConnector)

    def test_invalid_provider_names_rejected(self):
        for bad in ("Claude", "STUB", "", "a" * 33, "cla ude", "claude!",
                    None, 7):
            with self.assertRaises(InvalidProviderNameError, msg=repr(bad)):
                self.registry.register(bad, StubConnector)
        self.assertEqual(self.registry.providers(), ())

    def test_unknown_provider_rejected(self):
        with self.assertRaises(UnknownProviderError):
            self.registry.get("gemini")

    def test_lookup_also_rejects_non_canonical_names(self):
        with self.assertRaises(InvalidProviderNameError):
            self.registry.get("Stub")

    def test_registry_rejects_non_connector_classes(self):
        for bad in (object, "StubConnector", None):
            with self.assertRaises(TypeError, msg=repr(bad)):
                self.registry.register("stub", bad)
        self.assertEqual(self.registry.providers(), ())

    def test_registries_are_independent(self):
        other = ConnectorRegistry()
        self.registry.register("stub", StubConnector)
        with self.assertRaises(UnknownProviderError):
            other.get("stub")


class TrustBoundaryTests(unittest.TestCase):
    def _claim_kwargs(self):
        return {
            "device_uid": UID_A,
            "provider": "stub",
            "source_event_id": "native-1",
            "model": "stub-model",
            "started_at": datetime.fromisoformat(T1),
            "ended_at": datetime.fromisoformat(T2),
            "session_ref": "session",
        }

    def test_server_owned_fields_are_rejected(self):
        kwargs = self._claim_kwargs()
        for field in SERVER_OWNED_FIELDS:
            with self.assertRaises(ValidationError, msg=field):
                UsageEventClaim(**{**kwargs, field: "spoof"})

    def test_p1b_style_attributes_do_not_exist_on_claims(self):
        connector = StubConnector(device_uid=UID_A)
        raw = next(connector.discover(Path(tempfile.gettempdir())))
        claim = connector.normalize(raw)
        for attribute in ("attribution_confidence", "lineage",
                          "quota_pressure", "recommendation"):
            self.assertFalse(hasattr(claim, attribute), attribute)


class SourceBoundaryTests(unittest.TestCase):
    def _trees(self):
        return [
            (path, ast.parse(path.read_text(encoding="utf-8"),
                             filename=str(path)))
            for path in sorted(CONNECTORS_DIR.glob("*.py"))
        ]

    def test_framework_files_present(self):
        files = {path.name for path, _ in self._trees()}
        self.assertLessEqual({"__init__.py", "base.py", "registry.py"}, files)

    def test_forbidden_imports_are_absent(self):
        for path, tree in self._trees():
            overlap = sorted(_import_segments(tree)
                             & _FORBIDDEN_IMPORT_ROOTS)
            self.assertEqual(overlap, [], f"{path.name} imports {overlap}")

    def test_p1b_symbols_are_absent(self):
        for path, tree in self._trees():
            names = _code_identifiers(tree)
            hits = sorted({token for token in _FORBIDDEN_SYMBOL_TOKENS
                           for name in names if token in name})
            self.assertEqual(hits, [], f"{path.name} identifiers hit {hits}")


class ConnectorIngestIntegrationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "split.db"
        self.db = split_db.connect(path=self.db_path)
        self.db.execute(
            "INSERT INTO organizations (id,name,status,created_at,updated_at)"
            " VALUES ('org-a','Test A','active','t','t')")
        self.db.execute(
            "INSERT INTO devices (id,organization_id,device_uid,display_name,"
            "hostname_hash,username_hash,os,arch,first_seen_at,last_seen_at,"
            "status,identity_confidence,collector_version,created_at,"
            "updated_at) VALUES ('dev-a','org-a',?,'Test Device','hk1:a',"
            "'hk1:b','Linux','x86_64','t','t','active',0,'','t','t')",
            (UID_A,))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self._tmp.cleanup()

    def _claim(self, connector):
        raw = next(connector.discover(Path(self._tmp.name)))
        return connector.normalize(raw)

    def test_claim_reaches_usage_event_only_via_ingest(self):
        connector = StubConnector(device_uid=UID_A)
        result = ingest_usage_event(
            self.db, context=ServerContext("org-a", "actor-a"),
            claim=self._claim(connector))
        self.assertEqual(result.status, "created")
        self.assertIs(type(result.event), UsageEvent)
        self.assertEqual(result.event.source_event_id, "stub:native-stub-1")
        self.assertIsNone(result.event.member_id)
        self.assertIsNone(result.event.pricing_version)
        self.assertIsNone(result.event.api_equivalent_cost_usd)
        replay = ingest_usage_event(
            self.db, context=ServerContext("org-a", "actor-a"),
            claim=self._claim(connector))
        self.assertEqual(replay.status, "duplicate")
        self.assertEqual(replay.event.id, result.event.id)

    def test_claim_for_unregistered_device_fails_ingest(self):
        connector = StubConnector(device_uid=UID_B)
        with self.assertRaises(TenantViolation):
            ingest_usage_event(
                self.db, context=ServerContext("org-a", "actor-a"),
                claim=self._claim(connector))


if __name__ == "__main__":
    unittest.main(verbosity=2)
