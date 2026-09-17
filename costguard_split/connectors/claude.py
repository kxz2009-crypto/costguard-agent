"""P1A-05 Claude Code local transcript connector.

Reads Claude Code JSONL transcripts under ``<home>/projects/*/*.jsonl`` and
normalizes assistant usage records into UsageEventClaim values. Local files
are read-only inputs; prompt/response content never enters the claim
envelope, and nothing here performs I/O beyond reading local files.

Format contract (Claude Code transcript line, ``type == "assistant"``):
sessionId, version, timestamp (RFC3339 Z), message.id, message.model,
message.usage{input_tokens, cache_creation_input_tokens,
cache_read_input_tokens, output_tokens}. Mapping follows spec section 7.3:
cache read -> cached_input_tokens, cache write -> cache_write_tokens,
all five classes always present. reasoning_tokens is not exposed by the
provider and is explicitly 0. request_count is 1 per assistant message.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from .base import BaseConnector, RawUsage
from ..schemas.usage import UsageEventClaim

__all__ = ("ClaudeConnector",)

_COLLECTOR = "costguard-split-claude"


def _parse_ts(value: object, field: str) -> datetime:
    """Parse an RFC3339 timestamp; naive values are rejected."""
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
    """Token counter policy: true ints only; bool/float/str/negative die."""
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


class ClaudeConnector(BaseConnector):
    """Claude Code transcript -> UsageEventClaim (local, offline)."""

    name = "claude"

    def discover(self, home: Path,
                 since: Optional[datetime] = None) -> Iterable[RawUsage]:
        root = Path(home) / "projects"
        if not root.is_dir():
            return
        for path in sorted(root.glob("*/*.jsonl")):
            yield from self._read_file(path, since=since)

    def _read_file(self, path: Path,
                   since: Optional[datetime]) -> Iterable[RawUsage]:
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
                envelope = self._envelope(record)
                if envelope is None:
                    continue
                if since is not None and envelope["timestamp"] < since:
                    continue
                yield RawUsage(payload=envelope)

    @staticmethod
    def _envelope(record: object) -> Optional[dict]:
        """Whitelist-extract usage facts; content never enters the envelope."""
        if not isinstance(record, dict) or record.get("type") != "assistant":
            return None
        message = record.get("message")
        if not isinstance(message, dict):
            return None
        usage = message.get("usage")
        if not isinstance(usage, dict):
            return None
        return {
            "session_ref": _required_text(
                record.get("sessionId"), "sessionId"),
            "message_id": _required_text(message.get("id"), "message.id"),
            "model": _required_text(message.get("model"), "message.model"),
            "timestamp": _parse_ts(record.get("timestamp"), "timestamp"),
            "collector_version": _required_text(
                record.get("version"), "version"),
            "input_tokens": _token(
                usage.get("input_tokens"), "usage.input_tokens"),
            "cached_input_tokens": _token(
                usage.get("cache_read_input_tokens"),
                "usage.cache_read_input_tokens"),
            "cache_write_tokens": _token(
                usage.get("cache_creation_input_tokens"),
                "usage.cache_creation_input_tokens"),
            "output_tokens": _token(
                usage.get("output_tokens"), "usage.output_tokens"),
            "reasoning_tokens": 0,
        }

    def normalize(self, raw: RawUsage) -> UsageEventClaim:
        envelope = raw.payload
        started = envelope["timestamp"]
        return UsageEventClaim(
            device_uid=self.device_uid,
            provider=self.name,
            source_event_id=envelope["message_id"],
            model=envelope["model"],
            started_at=started,
            ended_at=started,
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
        message_id = raw.payload.get("message_id")
        return str(message_id) if message_id else None
