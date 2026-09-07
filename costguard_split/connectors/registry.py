"""P1A-04 provider -> connector registry.

Explicit, deterministic registration only: no auto-discovery, no network
probing, no silent overrides. Provider keys use the same canonical charset
as ``canonical_source_event_id`` so a registered provider always produces
exactly one stable idempotency prefix.
"""

from __future__ import annotations

import re

from .base import BaseConnector

__all__ = (
    "ConnectorRegistry",
    "ConnectorRegistryError",
    "DuplicateProviderError",
    "InvalidProviderNameError",
    "UnknownProviderError",
)

_PROVIDER_NAME = re.compile(r"[a-z0-9_-]{1,32}")


class ConnectorRegistryError(Exception):
    """Base class for registry failures."""


class InvalidProviderNameError(ConnectorRegistryError):
    """Provider key is not canonical lowercase [a-z0-9_-]{1,32}."""


class DuplicateProviderError(ConnectorRegistryError):
    """The provider key is already registered."""


class UnknownProviderError(ConnectorRegistryError):
    """No connector is registered under this provider key."""


def _canonical_provider(provider: str) -> str:
    if not isinstance(provider, str) or not _PROVIDER_NAME.fullmatch(provider):
        raise InvalidProviderNameError(
            "provider must match [a-z0-9_-]{1,32}, got "
            f"{provider!r}; names are never auto-normalized")
    return provider


class ConnectorRegistry:
    """Explicit provider-keyed registry of BaseConnector classes."""

    def __init__(self) -> None:
        self._connectors: dict[str, type[BaseConnector]] = {}

    def register(self, provider: str, connector: type[BaseConnector]) -> None:
        """Register a connector class under a canonical provider key."""
        key = _canonical_provider(provider)
        if not (isinstance(connector, type)
                and issubclass(connector, BaseConnector)):
            raise TypeError(
                "connector must be a BaseConnector subclass, got "
                f"{connector!r}")
        if key in self._connectors:
            raise DuplicateProviderError(
                f"provider already registered: {key!r}")
        self._connectors[key] = connector

    def get(self, provider: str) -> type[BaseConnector]:
        """Return the connector class registered for ``provider``."""
        key = _canonical_provider(provider)
        connector = self._connectors.get(key)
        if connector is None:
            raise UnknownProviderError(
                f"no connector registered for provider {key!r}")
        return connector

    def providers(self) -> tuple[str, ...]:
        """All registered provider keys, sorted."""
        return tuple(sorted(self._connectors))
