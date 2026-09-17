"""P1A-04/P1A-05 connector framework: local provider records -> claims.

Trust boundary: connectors never produce UsageEvent, never call the ingest
service, never touch pricing or money, and never hold server authority
fields. Only normalized claims cross this package's edge.
"""

from .base import BaseConnector, RawUsage
from .claude import ClaudeConnector
from .codex import CodexConnector
from .registry import (
    ConnectorRegistry,
    ConnectorRegistryError,
    DuplicateProviderError,
    InvalidProviderNameError,
    UnknownProviderError,
    default_registry,
)

__all__ = (
    "BaseConnector",
    "RawUsage",
    "ClaudeConnector",
    "CodexConnector",
    "ConnectorRegistry",
    "ConnectorRegistryError",
    "DuplicateProviderError",
    "InvalidProviderNameError",
    "UnknownProviderError",
    "default_registry",
)
