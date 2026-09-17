"""Isolated real SQLite input for legacy report/export integration tests."""

from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from costguard_agent import database
from costguard_agent.usage_event import UsageEvent


@contextmanager
def synthetic_usage():
    with TemporaryDirectory() as td:
        with patch.object(database, "CG_DIR", Path(td)), patch.object(
            database, "DB_PATH", Path(td) / "usage.db"
        ):
            events = [
                UsageEvent(source="codex", provider="openai", model="gpt-5.5",
                           input_tokens=1_000_000, output_tokens=1_000_000,
                           timestamp="2026-09-04T12:00:00+00:00",
                           session_ref="synthetic-priced"),
                UsageEvent(source="hermes", provider="UNKNOWN",
                           model="synthetic-unpriced", input_tokens=20,
                           output_tokens=10,
                           timestamp="2026-09-04T13:00:00+00:00",
                           session_ref="synthetic-unknown"),
            ]
            assert database.store(events) == (2, 2)
            yield
