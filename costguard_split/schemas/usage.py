"""P1A-02 collector-to-server UsageEventClaim boundary.

This is the only sanctioned collector wire shape. It contains usage facts and
non-authoritative collector metadata only; tenant/device/member ownership,
server timestamps, pricing, money, and any attribution authority are absent and
therefore rejected by ``extra='forbid'``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)

from ..identity.device_uid import validate_device_uid

NonNegativeInt = Annotated[StrictInt, Field(ge=0)]

CLAIM_FIELDS = (
    "device_uid",
    "provider",
    "source_event_id",
    "model",
    "started_at",
    "ended_at",
    "session_ref",
    "input_tokens",
    "cached_input_tokens",
    "cache_write_tokens",
    "output_tokens",
    "reasoning_tokens",
    "request_count",
    "provider_account_ref",
    "collector_version",
    "source_type",
)

# Documentation/audit aid. These are intentionally NOT model fields; attempts
# to submit them are rejected by the closed whitelist.
SERVER_OWNED_FIELDS = (
    "organization_id",
    "device_id",
    "member_id",
    "received_at",
    "created_at",
    "pricing_version",
    "api_equivalent_cost_usd",
)


class UsageEventClaim(BaseModel):
    """Strict collector claim containing facts, never server authority."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        frozen=True,
    )

    device_uid: str
    provider: str
    source_event_id: str | None = None
    model: str
    started_at: datetime
    ended_at: datetime
    session_ref: str
    input_tokens: NonNegativeInt = 0
    cached_input_tokens: NonNegativeInt = 0
    cache_write_tokens: NonNegativeInt = 0
    output_tokens: NonNegativeInt = 0
    reasoning_tokens: NonNegativeInt = 0
    request_count: NonNegativeInt = 1
    provider_account_ref: str | None = None
    collector_version: str = ""
    source_type: Literal["connector", "import", "manual"] = "connector"

    @field_validator("device_uid")
    @classmethod
    def _valid_device_uid(cls, value: str) -> str:
        if not validate_device_uid(value):
            raise ValueError("device_uid must be canonical cgdev_<uuid>")
        return value

    @field_validator("provider", "model", "session_ref")
    @classmethod
    def _required_text(cls, value: str) -> str:
        if not value:
            raise ValueError("field must not be blank")
        return value

    @field_validator("source_event_id", "provider_account_ref")
    @classmethod
    def _optional_text(cls, value: str | None) -> str | None:
        if value == "":
            raise ValueError("optional identifier must not be blank")
        return value

    @field_validator("started_at", "ended_at")
    @classmethod
    def _aware_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a timezone offset")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def _valid_interval(self) -> "UsageEventClaim":
        if self.ended_at < self.started_at:
            raise ValueError("ended_at must be greater than or equal to started_at")
        return self
