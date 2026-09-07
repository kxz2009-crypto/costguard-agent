"""P1A-04 connector framework base contract.

Connectors are local, offline adapters that turn provider-native usage
records into :class:`UsageEventClaim` values and nothing else. They never
produce UsageEvent objects, never call the ingest service, never read or
compute pricing/money, and never hold server authority: organization,
device, member, received/created timestamps, and pricing fields do not
exist inside this package.

``device_uid`` is injected at construction time by the local host process
(which resolves it through the identity layer); a connector can therefore
only ever claim usage FOR the device it was constructed for and cannot
invent device identity. Raw provider data stays local: RawUsage is an
in-memory, deep-frozen envelope that is never persisted, never audited,
and never leaves the machine -- only normalized claims do.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from ..identity.device_uid import validate_device_uid
from ..schemas.usage import UsageEventClaim

__all__ = ("BaseConnector", "RawUsage")


@dataclass(frozen=True)
class RawUsage:
    """One provider-native usage record, parsed but not yet normalized.

    LOCAL-ONLY by contract: never persisted, never audited, never sent to
    the server. The payload envelope is deep-frozen at construction so raw
    provider data cannot be mutated in place after parsing.
    """

    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "payload", MappingProxyType(dict(self.payload)))


class BaseConnector(ABC):
    """Abstract local connector (spec section 7.2).

    Subclasses provide provider-keyed parsing only. Everything server-side
    (tenancy, member attribution, timestamps, idempotency, pricing) is
    resolved downstream by the ingest service.
    """

    #: Canonical lowercase provider key (claude|codex|...). Validated by the
    #: registry at registration time; never a display name.
    name: str

    def __init__(self, *, device_uid: str) -> None:
        if not validate_device_uid(device_uid):
            raise ValueError(
                "device_uid must be a canonical cgdev_<uuid> string")
        self._device_uid = device_uid

    @property
    def device_uid(self) -> str:
        """The only device identity this connector may ever claim for."""
        return self._device_uid

    @abstractmethod
    def discover(self, home: Path,
                 since: datetime | None = None) -> Iterable[RawUsage]:
        """Yield provider-native usage records found under ``home``.

        Read-only, offline, lazily evaluated. ``since`` is an opaque filter
        hint for the provider implementation; malformed records must be
        surfaced to the caller, never silently skipped.
        """

    @abstractmethod
    def normalize(self, raw: RawUsage) -> UsageEventClaim:
        """Map one raw record into a validated UsageEventClaim.

        Must be pure and deterministic. Token classes map explicitly
        (missing class = 0, never an omitted column), timestamps must be
        timezone-aware, and the claim's device identity is always
        ``self.device_uid``.
        """

    @abstractmethod
    def native_event_id(self, raw: RawUsage) -> str | None:
        """Return the provider-native unique event id when one exists.

        Return None when the provider has no native id; the ingest service
        then derives a deterministic, payload-sensitive id.
        """
