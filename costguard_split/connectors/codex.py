"""P1A-06 Codex CLI local rollout connector.

Reads Codex rollout JSONL under ``<home>/sessions/**/*.jsonl`` and emits one
UsageEventClaim per API call. Format confirmed against current live
artifacts:

- ``session_meta`` line: session_id / id, cli_version (type at top level)
- ``turn_context`` line: turn_id, model, line timestamp = turn start
  (type at top level; turn ids may repeat within one file after
  resume/compaction, so turn ids are NOT event identities)
- ``token_count`` event (top level ``event_msg``, ``payload.type`` ==
  ``token_count``) with ``info.last_token_usage`` = exactly one API call:
  input_tokens, cached_input_tokens, cache_write_input_tokens,
  output_tokens, reasoning_output_tokens (reasoning is an output subset)

Event granularity: one claim per token_count (per API request). Collapsing
a whole turn into its last token_count both undercounts real usage and
collides on repeated turn ids. The native event id is
``<turn_id>:<token_count UTC timestamp>`` -- stable across rescans,
unique per call. ``info: null`` lines are session bookkeeping and are
skipped; ``rate_limits`` and ``total_token_usage`` are quota / cumulative
domains and never enter claims. Local files only; prompt / response
content never enters the envelope.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from .base import BaseConnector, RawUsage
from ..schemas.usage import UsageEventClaim

__all__ = ("CodexConnector",)


def _parse_ts(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty timestamp string")
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(
            f"{field} is not a valid RFC3339 timestamp: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _token(value: object, field: str, default: int = 0) -> int:
    if value is None:
        return default
    if type(value) is not int:
        raise ValueError(
            f"{field} must be an integer, got {type(value).__name__}")
    if value < 0:
        raise ValueError(f"{field} must be >= 0, got {value}")
    return value


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


class _Turn:
    """Current turn scope inside one file (never leaves discover())."""

    __slots__ = ("turn_id", "model", "started_at")

    def __init__(self, *, turn_id: str, model: str,
                 started_at: datetime) -> None:
        self.turn_id = turn_id
        self.model = model
        self.started_at = started_at


class CodexConnector(BaseConnector):
    """Codex rollout file -> UsageEventClaim stream (local, offline)."""

    name = "codex"

    def discover(self, home: Path,
                 since: Optional[datetime] = None) -> Iterable[RawUsage]:
        root = Path(home) / "sessions"
        if not root.is_dir():
            return
        for path in sorted(root.glob("**/*.jsonl")):
            yield from self._read_file(path, since=since)

    def _read_file(self, path: Path,
                   since: Optional[datetime]) -> Iterable[RawUsage]:
        session_ref: Optional[str] = None
        collector_version: Optional[str] = None
        turn: Optional[_Turn] = None

        with path.open("r", encoding="utf-8", errors="strict") as handle:
            for lineno, line in enumerate(handle, start=1):
                if not line.endswith("\n"):
                    # Torn trailing write from an active session: not a
                    # complete record yet, retried on the next run.
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"{path.name}:{lineno}: malformed JSONL line"
                    ) from exc
                if not isinstance(record, dict):
                    continue
                payload = record.get("payload")
                if not isinstance(payload, dict):
                    continue
                # Current rollouts carry payload.type for token_count
                # (top-level event_msg) and no payload.type on session_meta
                # / turn_context; payload.type wins, top level is the
                # fallback. Both historic layouts classify correctly.
                kind = payload.get("type") or record.get("type")

                if kind == "session_meta":
                    session_ref = _required_text(
                        payload.get("session_id") or payload.get("id"),
                        "session_meta.session_id")
                    collector_version = _required_text(
                        payload.get("cli_version"),
                        "session_meta.cli_version")
                    turn = None
                    continue

                if kind == "turn_context":
                    if session_ref is None:
                        # turn_context before session_meta: unusable file
                        # prefix; the session header is authoritative.
                        raise ValueError(
                            f"{path.name}:{lineno}: turn_context before "
                            "session_meta")
                    turn = _Turn(
                        turn_id=_required_text(
                            payload.get("turn_id"), "turn_context.turn_id"),
                        model=_required_text(
                            payload.get("model"), "turn_context.model"),
                        started_at=_parse_ts(
                            record.get("timestamp"),
                            "turn_context.timestamp"),
                    )
                    continue

                if kind == "token_count":
                    if turn is None:
                        continue  # usage before any turn context
                    info = payload.get("info")
                    if not isinstance(info, dict):
                        continue  # bookkeeping line, no usage facts
                    last = info.get("last_token_usage")
                    if not isinstance(last, dict):
                        continue
                    ended_at = _parse_ts(
                        record.get("timestamp"), "token_count.timestamp")
                    envelope = {
                        "session_ref": session_ref,
                        "collector_version": collector_version,
                        "turn_id": turn.turn_id,
                        "native_id": (
                            f"{turn.turn_id}:"
                            f"{ended_at.isoformat()}"),
                        "model": turn.model,
                        "started_at": turn.started_at,
                        "ended_at": ended_at,
                        "input_tokens": _token(
                            last.get("input_tokens"),
                            "last_token_usage.input_tokens"),
                        "cached_input_tokens": _token(
                            last.get("cached_input_tokens"),
                            "last_token_usage.cached_input_tokens"),
                        "cache_write_tokens": _token(
                            last.get("cache_write_input_tokens"),
                            "last_token_usage.cache_write_input_tokens"),
                        "output_tokens": _token(
                            last.get("output_tokens"),
                            "last_token_usage.output_tokens"),
                        "reasoning_tokens": _token(
                            last.get("reasoning_output_tokens"),
                            "last_token_usage.reasoning_output_tokens"),
                    }
                    if since is not None and ended_at < since:
                        continue
                    yield RawUsage(payload=envelope)

    def normalize(self, raw: RawUsage) -> UsageEventClaim:
        envelope = raw.payload
        return UsageEventClaim(
            device_uid=self.device_uid,
            provider=self.name,
            source_event_id=envelope["native_id"],
            model=envelope["model"],
            started_at=envelope["started_at"],
            ended_at=envelope["ended_at"],
            session_ref=envelope["session_ref"],
            input_tokens=envelope["input_tokens"],
            cached_input_tokens=envelope["cached_input_tokens"],
            cache_write_tokens=envelope["cache_write_tokens"],
            output_tokens=envelope["output_tokens"],
            reasoning_tokens=envelope["reasoning_tokens"],
            request_count=1,
            collector_version=envelope["collector_version"],
            source_type="connector",
        )

    def native_event_id(self, raw: RawUsage) -> Optional[str]:
        native_id = raw.payload.get("native_id") or raw.payload.get("turn_id")
        return str(native_id) if native_id else None
