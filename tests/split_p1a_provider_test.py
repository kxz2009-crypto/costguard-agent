"""P1A-05 provider connector tests (Claude + Codex).

Fixtures are synthetic minimal transcripts shaped after the real formats:
- Claude Code transcript JSONL (type=assistant, message.usage with cache
  read/write keys) -- format not verifiable against local artifacts on this
  machine, so the fixture itself pins the accepted contract.
- Codex rollout JSONL (session_meta / turn_context / token_count with
  info.last_token_usage) -- keys mirror live artifacts.

Covers: instantiation, discover output, normalize mapping, token mapping,
native ids, timestamp policy, token-counter policy, server-owned field
rejection, registry wiring, provider-name consistency, and P1B symbol
scans.
"""

from __future__ import annotations

import ast
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from costguard_split.connectors import (
    BaseConnector,
    ClaudeConnector,
    CodexConnector,
    ConnectorRegistry,
    InvalidProviderNameError,
    RawUsage,
    UnknownProviderError,
    default_registry,
)
from costguard_split.ingest.service import (
    _source_event_id,
)  # white-box: derived-id parity check
from costguard_split.schemas.usage import SERVER_OWNED_FIELDS, UsageEventClaim

UID = "cgdev_018f0c9a-1605-4bec-8000-17b71faba7e1"
T1 = "2026-09-10T00:00:00+00:00"
T2 = "2026-09-10T00:01:30+00:00"
T3 = "2026-09-10T00:03:00+00:00"
CONNECTORS_DIR = (
    Path(__file__).resolve().parents[1] / "costguard_split" / "connectors")

_FORBIDDEN_IMPORT_ROOTS = frozenset((
    "ingest", "pricing", "models", "api",
    "urllib", "socket", "ssl", "http", "httpx", "requests", "subprocess",
))
_FORBIDDEN_SYMBOL_TOKENS = (
    "attribution", "lineage", "confidence", "quota", "recommendation",
    "optimization", "pricing", "cost", "money",
)


def _claude_record(**overrides):
    record = {
        "type": "assistant",
        "sessionId": "11111111-2222-3333-4444-555555555555",
        "version": "2.0.14",
        "uuid": "row-uuid-1",
        "timestamp": "2026-09-10T00:00:00.500Z",
        "message": {
            "id": "msg_01ABC",
            "model": "claude-sonnet-4-5",
            "role": "assistant",
            "content": [{"type": "text", "text": "SHOULD-NOT-LEAK"}],
            "usage": {
                "input_tokens": 100,
                "cache_creation_input_tokens": 40,
                "cache_read_input_tokens": 2000,
                "output_tokens": 300,
            },
        },
    }
    record.update(overrides)
    return record


def _codex_lines(**overrides):
    meta = {
        "type": "session_meta",
        "timestamp": "2026-09-10T00:00:00.100Z",
        "payload": {
            "type": "session_meta",
            "session_id": "019fb1e2-56e9-79a1-af01-2b39ec252e9f",
            "id": "019fb1e2-56e9-79a1-af01-2b39ec252e9f",
            "cli_version": "0.146.0",
            "model_provider": "openai",
        },
    }
    turn = {
        "type": "turn_context",
        "timestamp": "2026-09-10T00:00:05.000Z",
        "payload": {
            "type": "turn_context",
            "turn_id": "019fb1e2-5dda-70f0-ab1a-d3517a3a1249",
            "model": "gpt-5-codex",
            "cwd": "SHOULD-NOT-LEAK",
        },
    }
    tokens = {
        "type": "token_count",
        "timestamp": "2026-09-10T00:00:12.000Z",
        "payload": {
            "type": "token_count",
            "info": {
                "last_token_usage": {
                    "input_tokens": 500,
                    "cached_input_tokens": 400,
                    "cache_write_input_tokens": 30,
                    "output_tokens": 900,
                    "reasoning_output_tokens": 350,
                    "total_tokens": 1830,
                },
                "total_token_usage": {"input_tokens": 999999},
                "model_context_window": 258400,
            },
            "rate_limits": {"primary": {"used_percent": 10.0}},
        },
    }
    for key, value in overrides.items():
        if key == "turn":
            turn["payload"].update(value)
        elif key == "tokens":
            tokens["payload"]["info"]["last_token_usage"].update(value)
        elif key == "turn_ts":
            turn["timestamp"] = value
        elif key == "tokens_ts":
            tokens["timestamp"] = value
    return [meta, turn, tokens]


def _write_jsonl(path: Path, records) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")


class _HomeTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


class ClaudeConnectorTests(_HomeTestCase):
    def setUp(self):
        super().setUp()
        self.connector = ClaudeConnector(device_uid=UID)

    def test_instantiation_requires_base_identity(self):
        self.assertEqual(self.connector.name, "claude")
        with self.assertRaises(ValueError):
            ClaudeConnector(device_uid="hostname-guess")

    def test_discover_finds_project_transcripts(self):
        _write_jsonl(self.home / "projects" / "proj-a" / "t.jsonl",
                     [_claude_record(), _claude_record()])
        _write_jsonl(self.home / "projects" / "proj-b" / "u.jsonl",
                     [_claude_record()])
        raws = list(self.connector.discover(self.home))
        self.assertEqual(len(raws), 3)
        self.assertTrue(all(isinstance(r, RawUsage) for r in raws))
        self.assertEqual(list(self.connector.discover(self.home / "nope")), [])

    def test_discover_skips_non_assistant_and_content_never_leaks(self):
        _write_jsonl(self.home / "projects" / "p" / "t.jsonl", [
            {"type": "user", "message": {"content": "secret prompt"}},
            _claude_record(),
            {"type": "summary", "summary": "secret summary"},
        ])
        raws = list(self.connector.discover(self.home))
        self.assertEqual(len(raws), 1)
        blob = json.dumps(dict(raws[0].payload), default=str)
        self.assertNotIn("SHOULD-NOT-LEAK", blob)
        self.assertNotIn("secret", blob)

    def test_normalize_maps_all_token_classes_and_identity(self):
        (self.home / "projects" / "p").mkdir(parents=True)
        (self.home / "projects" / "p" / "t.jsonl").write_text(
            json.dumps(_claude_record()) + "\n", encoding="utf-8")
        raw = next(self.connector.discover(self.home))
        claim = self.connector.normalize(raw)
        self.assertIs(type(claim), UsageEventClaim)
        self.assertEqual(claim.provider, "claude")
        self.assertEqual(claim.device_uid, UID)
        self.assertEqual(claim.source_event_id, "msg_01ABC")
        self.assertEqual(claim.model, "claude-sonnet-4-5")
        self.assertEqual(claim.session_ref,
                         "11111111-2222-3333-4444-555555555555")
        self.assertEqual(claim.input_tokens, 100)
        self.assertEqual(claim.cached_input_tokens, 2000)
        self.assertEqual(claim.cache_write_tokens, 40)
        self.assertEqual(claim.output_tokens, 300)
        self.assertEqual(claim.reasoning_tokens, 0)
        self.assertEqual(claim.request_count, 1)
        self.assertEqual(claim.collector_version, "2.0.14")
        self.assertEqual(claim.source_type, "connector")
        self.assertEqual(claim.started_at.utcoffset(), timezone.utc.utcoffset(None))
        self.assertEqual(claim.ended_at, claim.started_at)

    def test_native_event_id(self):
        _write_jsonl(self.home / "projects" / "p" / "t.jsonl",
                     [_claude_record()])
        raw = next(self.connector.discover(self.home))
        self.assertEqual(self.connector.native_event_id(raw), "msg_01ABC")
        missing = RawUsage(payload={"session_ref": "s"})
        self.assertIsNone(self.connector.native_event_id(missing))

    def test_naive_and_missing_timestamps_rejected(self):
        naive = {
            "session_ref": "s", "message_id": "m", "model": "x",
            "timestamp": "2026-09-10T00:00:00",  # no offset
            "collector_version": "v", "input_tokens": 1,
            "cached_input_tokens": 0, "cache_write_tokens": 0,
            "output_tokens": 2, "reasoning_tokens": 0,
        }
        with self.assertRaises(ValueError):
            self.connector.normalize(RawUsage(payload=naive))
        with self.assertRaises(ValueError):
            self.connector._envelope({"type": "assistant",
                                      "message": {"usage": {}}})

    def test_bad_token_counters_rejected(self):
        for bad in (True, False, 1.5, "7", -1):
            usage = {"input_tokens": bad, "output_tokens": 1}
            with self.assertRaises(ValueError, msg=repr(bad)):
                self.connector._envelope({
                    "type": "assistant", "sessionId": "s",
                    "version": "v", "timestamp": T1,
                    "message": {"id": "m", "model": "x", "usage": usage}})

    def test_torn_trailing_line_is_ignored_until_complete(self):
        text = json.dumps(_claude_record()) + "\n" + json.dumps(
            _claude_record())[:40]
        path = self.home / "projects" / "p" / "t.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text(text, encoding="utf-8")
        self.assertEqual(len(list(self.connector.discover(self.home))), 1)

    def test_malformed_json_line_raises(self):
        path = self.home / "projects" / "p" / "t.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text("{not json}\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            list(self.connector.discover(self.home))

    def test_since_filter(self):
        _write_jsonl(self.home / "projects" / "p" / "t.jsonl",
                     [_claude_record()])
        cutoff = datetime(2026, 9, 11, tzinfo=timezone.utc)
        self.assertEqual(list(self.connector.discover(self.home,
                                                      since=cutoff)), [])


class CodexConnectorTests(_HomeTestCase):
    def setUp(self):
        super().setUp()
        self.connector = CodexConnector(device_uid=UID)

    def test_instantiation_requires_base_identity(self):
        self.assertEqual(self.connector.name, "codex")
        with self.assertRaises(ValueError):
            CodexConnector(device_uid="hostname-guess")

    def test_discover_and_normalize_full_turn(self):
        _write_jsonl(
            self.home / "sessions" / "2026" / "09" / "10" / "r.jsonl",
            _codex_lines())
        raws = list(self.connector.discover(self.home))
        self.assertEqual(len(raws), 1)
        claim = self.connector.normalize(raws[0])
        self.assertIs(type(claim), UsageEventClaim)
        self.assertEqual(claim.provider, "codex")
        self.assertEqual(claim.device_uid, UID)
        self.assertEqual(claim.source_event_id,
                         "019fb1e2-5dda-70f0-ab1a-d3517a3a1249:"
                         "2026-09-10T00:00:12+00:00")
        self.assertEqual(claim.model, "gpt-5-codex")
        self.assertEqual(claim.session_ref,
                         "019fb1e2-56e9-79a1-af01-2b39ec252e9f")
        self.assertEqual(claim.input_tokens, 500)
        self.assertEqual(claim.cached_input_tokens, 400)
        self.assertEqual(claim.cache_write_tokens, 30)
        self.assertEqual(claim.output_tokens, 900)
        self.assertEqual(claim.reasoning_tokens, 350)
        self.assertEqual(claim.request_count, 1)
        self.assertEqual(claim.collector_version, "0.146.0")
        self.assertEqual(
            claim.started_at.isoformat(),
            datetime.fromisoformat("2026-09-10T00:00:05+00:00").isoformat())
        self.assertEqual(
            claim.ended_at.isoformat(),
            datetime.fromisoformat("2026-09-10T00:00:12+00:00").isoformat())
        # envelope carries no raw content, cwd, quota or cumulative domains
        blob = json.dumps(dict(raws[0].payload), default=str)
        self.assertNotIn("SHOULD-NOT-LEAK", blob)
        self.assertNotIn("rate_limits", blob)
        self.assertNotIn("total_token_usage", blob)
        self.assertNotIn("model_context_window", blob)

    def test_multi_turn_files_emit_one_claim_per_turn(self):
        records = []
        for i, (turn_id, tokens_ts) in enumerate((
                ("turn-1", "2026-09-10T00:00:12Z"),
                ("turn-2", "2026-09-10T00:01:40Z"))):
            lines = _codex_lines()
            lines[1]["payload"]["turn_id"] = turn_id
            lines[1]["timestamp"] = f"2026-09-10T00:0{i}:05Z"
            lines[2]["timestamp"] = tokens_ts
            records.extend(lines)
        _write_jsonl(self.home / "sessions" / "d" / "r.jsonl", records)
        claims = [self.connector.normalize(raw)
                  for raw in self.connector.discover(self.home)]
        self.assertEqual([c.source_event_id for c in claims],
                         ["turn-1:2026-09-10T00:00:12+00:00",
                          "turn-2:2026-09-10T00:01:40+00:00"])
        self.assertEqual([c.model for c in claims],
                         ["gpt-5-codex", "gpt-5-codex"])

    def test_each_token_count_is_one_event_and_last_wins_within_turn(self):
        first = _codex_lines()
        again = _codex_lines()
        again[2]["payload"]["info"]["last_token_usage"][
            "output_tokens"] = 1234
        again[2]["timestamp"] = "2026-09-10T00:00:20Z"
        # same turn: meta + turn_context from `first`, then two token_count
        # lines -- each is one API call, both must be emitted.
        _write_jsonl(self.home / "sessions" / "d" / "r.jsonl",
                     first[:2] + [first[2], again[2]])
        raws = list(self.connector.discover(self.home))
        self.assertEqual(len(raws), 2)
        claims = [self.connector.normalize(raw) for raw in raws]
        self.assertEqual([c.output_tokens for c in claims], [900, 1234])
        self.assertEqual(
            [c.ended_at.isoformat() for c in claims],
            ["2026-09-10T00:00:12+00:00", "2026-09-10T00:00:20+00:00"])
        self.assertEqual(len({c.source_event_id for c in claims}), 2)

    def test_null_info_and_orphan_usage_are_skipped(self):
        header = _codex_lines()
        bookkeeping = {"type": "token_count",
                       "timestamp": "2026-09-10T00:00:01Z",
                       "payload": {"type": "token_count", "info": None}}
        orphan_usage = {
            "type": "token_count",
            "timestamp": "2026-09-10T00:00:02Z",
            "payload": {"type": "token_count", "info": {
                "last_token_usage": {"input_tokens": 5,
                                     "output_tokens": 5}}}}
        _write_jsonl(self.home / "sessions" / "d" / "r.jsonl",
                     [bookkeeping, orphan_usage] + header)
        raws = list(self.connector.discover(self.home))
        self.assertEqual(len(raws), 1)
        self.assertEqual(self.connector.normalize(raws[0]).input_tokens, 500)

    def test_repeated_turn_id_across_segments_stays_unique(self):
        # Rollouts reuse turn ids after resume/compaction; the tc timestamp
        # in the native id keeps every API call event unique.
        first = _codex_lines()
        later = _codex_lines()
        later[1]["timestamp"] = "2026-09-10T01:00:05Z"  # new turn_context,
        later[2]["timestamp"] = "2026-09-10T01:00:12Z"  # same turn_id
        _write_jsonl(self.home / "sessions" / "d" / "r.jsonl", first + later)
        claims = [self.connector.normalize(raw)
                  for raw in self.connector.discover(self.home)]
        self.assertEqual(len(claims), 2)
        self.assertEqual(len({c.source_event_id for c in claims}), 2)

    def test_turn_context_before_session_meta_rejected(self):
        _write_jsonl(self.home / "sessions" / "d" / "r.jsonl",
                     _codex_lines()[1:])
        with self.assertRaises(ValueError):
            list(self.connector.discover(self.home))

    def test_naive_turn_timestamp_rejected(self):
        lines = _codex_lines(turn_ts="2026-09-10T00:00:05")  # no offset
        _write_jsonl(self.home / "sessions" / "d" / "r.jsonl", lines)
        with self.assertRaises(ValueError):
            list(self.connector.discover(self.home))

    def test_bad_token_counters_rejected(self):
        for index, bad in enumerate((True, 2.5, "9", -3)):
            lines = _codex_lines(tokens={"input_tokens": bad})
            path = self.home / "sessions" / f"case-{index}" / "r.jsonl"
            _write_jsonl(path, lines)
            with self.assertRaises(ValueError, msg=repr(bad)):
                list(self.connector.discover(self.home))

    def test_native_event_id(self):
        lines = _codex_lines()
        raw = RawUsage(payload={
            "session_ref": "s", "collector_version": "v",
            "turn_id": lines[1]["payload"]["turn_id"],
            "native_id": lines[1]["payload"]["turn_id"] + ":ts",
            "model": "m",
            "started_at": datetime.fromisoformat(T1),
            "ended_at": datetime.fromisoformat(T2),
            "input_tokens": 1, "cached_input_tokens": 0,
            "cache_write_tokens": 0, "output_tokens": 2,
            "reasoning_tokens": 0})
        self.assertEqual(self.connector.native_event_id(raw),
                         "019fb1e2-5dda-70f0-ab1a-d3517a3a1249:ts")
        self.assertIsNone(self.connector.native_event_id(
            RawUsage(payload={})))

    def test_multi_session_file_resets_session_context(self):
        first = _codex_lines()
        second_meta = dict(first[0])
        second_meta["payload"] = dict(first[0]["payload"])
        second_meta["payload"]["session_id"] = "second-session"
        orphan_turn = dict(first[1])
        orphan_turn["payload"] = dict(first[1]["payload"])
        orphan_turn["payload"]["turn_id"] = "turn-after-meta"
        # A second session_meta followed by a turn: emitted claim for the
        # first turn must flush before the reset takes effect.
        _write_jsonl(self.home / "sessions" / "d" / "r.jsonl",
                     first + [second_meta, orphan_turn])
        raws = list(self.connector.discover(self.home))
        self.assertEqual(len(raws), 1)
        self.assertEqual(raws[0].payload["session_ref"],
                         "019fb1e2-56e9-79a1-af01-2b39ec252e9f")
        self.assertEqual(raws[0].payload["turn_id"], "019fb1e2-5dda-70f0-ab1a-d3517a3a1249")

    def test_since_filter(self):
        _write_jsonl(self.home / "sessions" / "d" / "r.jsonl",
                     _codex_lines())
        cutoff = datetime(2026, 9, 11, tzinfo=timezone.utc)
        self.assertEqual(list(self.connector.discover(self.home,
                                                      since=cutoff)), [])


class RegistryAndBoundaryTests(unittest.TestCase):
    def test_default_registry_has_both_providers(self):
        registry = default_registry()
        self.assertIs(registry.get("claude"), ClaudeConnector)
        self.assertIs(registry.get("codex"), CodexConnector)
        self.assertEqual(registry.providers(), ("claude", "codex"))

    def test_registry_rejects_display_case_names(self):
        registry = ConnectorRegistry()
        for bad in ("Claude", "Codex", "CLAUDE", "gpt codex"):
            with self.assertRaises(InvalidProviderNameError, msg=bad):
                registry.register(bad, ClaudeConnector)
        self.assertEqual(registry.providers(), ())

    def test_connector_names_are_canonical(self):
        self.assertEqual(ClaudeConnector.name, "claude")
        self.assertEqual(CodexConnector.name, "codex")

    def test_normalize_output_type_is_plain_claim(self):
        connector = ClaudeConnector(device_uid=UID)
        envelope = {
            "session_ref": "s", "message_id": "m", "model": "x",
            "timestamp": datetime.fromisoformat(T1),
            "collector_version": "v", "input_tokens": 1,
            "cached_input_tokens": 0, "cache_write_tokens": 0,
            "output_tokens": 2, "reasoning_tokens": 0,
        }
        claim = connector.normalize(RawUsage(payload=envelope))
        self.assertIs(type(claim), UsageEventClaim)

    def test_server_owned_fields_rejected_on_claims(self):
        base = {
            "device_uid": UID, "provider": "claude",
            "source_event_id": "m", "model": "x",
            "started_at": datetime.fromisoformat(T1),
            "ended_at": datetime.fromisoformat(T2),
            "session_ref": "s",
        }
        for field in SERVER_OWNED_FIELDS:
            with self.assertRaises(ValidationError, msg=field):
                UsageEventClaim(**{**base, field: "spoof"})


class SourceBoundaryTests(unittest.TestCase):
    def _trees(self):
        return [
            (path, ast.parse(path.read_text(encoding="utf-8"),
                             filename=str(path)))
            for path in sorted(CONNECTORS_DIR.glob("*.py"))
        ]

    def test_provider_modules_exist(self):
        files = {path.name for path, _ in self._trees()}
        self.assertLessEqual({"claude.py", "codex.py"}, files)

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

    def test_normalize_returns_are_typed_as_claim(self):
        for path, tree in self._trees():
            if path.name not in ("claude.py", "codex.py"):
                continue
            returned = [
                node.returns.id
                for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "normalize" and node.returns
                and isinstance(node.returns, ast.Name)
            ]
            self.assertEqual(returned, ["UsageEventClaim"], path.name)


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
