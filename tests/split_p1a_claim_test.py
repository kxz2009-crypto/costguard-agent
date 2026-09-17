"""P1A-02 UsageEventClaim collector trust-boundary tests."""

from __future__ import annotations

import unittest

try:
    from pydantic import ValidationError
    _DEPS = True
except ImportError:  # pragma: no cover - optional [split-server] extra
    _DEPS = False

if _DEPS:
    from costguard_split.schemas.usage import (
        CLAIM_FIELDS,
        SERVER_OWNED_FIELDS,
        UsageEventClaim,
    )

from costguard_split.schemas import dto

UID = "cgdev_018f0c9a-1605-4bec-8000-17b71faba7e1"
T0 = "2026-09-01T00:00:00+00:00"
T1 = "2026-09-01T00:00:01+00:00"


def valid_claim(**overrides):
    payload = {
        "device_uid": UID,
        "provider": "claude",
        "source_event_id": "claude:event-a",
        "model": "test-model",
        "started_at": T0,
        "ended_at": T1,
        "session_ref": "session-a",
        "input_tokens": 10,
        "cached_input_tokens": 20,
        "cache_write_tokens": 30,
        "output_tokens": 40,
        "reasoning_tokens": 50,
        "request_count": 1,
        "provider_account_ref": "account-a",
        "collector_version": "test-collector",
        "source_type": "connector",
    }
    payload.update(overrides)
    return payload


@unittest.skipUnless(_DEPS, "pydantic v2 not installed ([split-server])")
class UsageEventClaimBoundaryTests(unittest.TestCase):
    def test_claim_accepts_only_documented_collector_fields(self):
        claim = UsageEventClaim.model_validate(valid_claim())
        self.assertEqual(set(claim.model_dump()), set(CLAIM_FIELDS))
        self.assertEqual(claim.cached_input_tokens, 20)
        self.assertNotIn("organization_id", claim.model_dump())
        self.assertNotIn("device_id", claim.model_dump())
        self.assertNotIn("member_id", claim.model_dump())

    def test_optional_metadata_defaults_are_non_authoritative(self):
        payload = valid_claim()
        for name in ("provider_account_ref", "collector_version", "source_type"):
            payload.pop(name)
        claim = UsageEventClaim.model_validate(payload)
        self.assertIsNone(claim.provider_account_ref)
        self.assertEqual(claim.collector_version, "")
        self.assertEqual(claim.source_type, "connector")

    def test_extra_fields_are_forbidden(self):
        with self.assertRaises(ValidationError) as raised:
            UsageEventClaim.model_validate(valid_claim(arbitrary_metadata={"x": 1}))
        self.assertEqual(raised.exception.errors()[0]["type"], "extra_forbidden")

    def test_server_authority_money_and_private_fields_are_all_rejected(self):
        forbidden = (
            "organization_id", "device_id", "member_id", "received_at",
            "created_at", "pricing_version", "api_equivalent_cost_usd",
            "cost", "price", "billing", "estimated_cost",
            "identity_confidence", "attribution_confidence", "confidence",
            "attribution", "automatic_attribution", "lineage",
            "lineage_id", "allocation", "prompt", "response", "content",
            "hostname", "username", "raw_ip", "public_ip", "local_ip",
            "metadata", "device_json",
        )
        self.assertLessEqual(set(SERVER_OWNED_FIELDS), set(forbidden))
        for field in forbidden:
            with self.subTest(field=field):
                with self.assertRaises(ValidationError) as raised:
                    UsageEventClaim.model_validate(valid_claim(**{field: "spoof"}))
                self.assertTrue(all(
                    error["type"] == "extra_forbidden"
                    for error in raised.exception.errors()))

    def test_every_counter_rejects_bool_float_string_and_negative(self):
        fields = (
            "input_tokens", "cached_input_tokens", "cache_write_tokens",
            "output_tokens", "reasoning_tokens", "request_count",
        )
        for field in fields:
            for invalid in (True, 1.0, "1", -1):
                with self.subTest(field=field, invalid=invalid):
                    with self.assertRaises(ValidationError):
                        UsageEventClaim.model_validate(
                            valid_claim(**{field: invalid}))

    def test_timestamps_must_be_timezone_aware_and_ordered(self):
        for field in ("started_at", "ended_at"):
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    UsageEventClaim.model_validate(
                        valid_claim(**{field: "2026-09-01T00:00:00"}))
        with self.assertRaises(ValidationError):
            UsageEventClaim.model_validate(valid_claim(started_at=T1, ended_at=T0))

    def test_required_strings_cannot_be_blank(self):
        for field in ("device_uid", "provider", "model", "started_at",
                      "ended_at", "session_ref"):
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    UsageEventClaim.model_validate(valid_claim(**{field: "  "}))

    def test_source_event_id_may_be_omitted_for_later_derivation(self):
        payload = valid_claim()
        payload.pop("source_event_id")
        claim = UsageEventClaim.model_validate(payload)
        self.assertIsNone(claim.source_event_id)

    def test_p0_import_path_reexports_the_canonical_model(self):
        self.assertIs(dto.UsageEventClaim, UsageEventClaim)
        claim = dto.UsageEventClaim(**valid_claim())
        self.assertEqual(claim.provider, "claude")


if __name__ == "__main__":
    unittest.main(verbosity=2)
