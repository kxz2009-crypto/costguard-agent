"""P1A-04 connector framework: local provider records -> UsageEventClaim.

Trust boundary: connectors never produce UsageEvent, never call the ingest
service, never touch pricing or money, and never hold server authority
fields. Only normalized claims cross this package's edge.
"""

from .base import BaseConnector, RawUsage
from .registry import (
    ConnectorRegistry,
    ConnectorRegistryError,
    DuplicateProviderError,
    InvalidProviderNameError,
    UnknownProviderError,
)

__all__ = (
    "BaseConnector",
    "RawUsage",
    "ConnectorRegistry",
    "ConnectorRegistryError",
    "DuplicateProviderError",
    "InvalidProviderNameError",
    "UnknownProviderError",
)
