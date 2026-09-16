# Delivery hardening follow-up — 2026-09-13

The owner requested continued work after the completion audit. This narrow
follow-up repairs packaging and guards; it does not authorize P1E implementation.

## Changes and installation

Include costguard_split and data/public_pricing.json in distribution builds.
The legacy CLI base installation retains zero dependencies. For Split ingestion,
connectors and claims use `pip install '.[split]'` (Pydantic); for HTTP adapters
use `pip install '.[split-server]'`.

Legacy summary/provider/model/trend routes return 404 when server context is
absent, before invoking analytics, matching the consumption adapter.
Added 12 regression cases and scripts/verify_split_install.py. Run the latter
with Python -I and a pip --target installation directory. Optional --claims and
--server checks require the corresponding dependencies in the interpreter.

## Validation

Original guards: 4 failures / 8 passes in new cases. Fixed guards: 12 passes.
Full staging regression: 325 passed, 2 skipped. Legacy contracts: 18 passed,
0 failed, 2 skipped. Two pytest checks require a Git checkout, absent in staging;
two contract checks require live connector fixtures, absent in isolated HOME.
These skips are not passes. Existing dependency deprecation warnings remain.

Wheel and sdist-rebuilt wheel each pass base, claims and HTTP checks, including
installed pricing data and missing-context 404. Loaded CostGuard modules resolve
to the installation target, never the checkout. Base uses system Python without
Pydantic; optional checks use the existing dependency-equipped venv. This is
not fresh dependency-resolution testing or a full Python-version matrix.

## Remaining boundaries

Fixed server organization context is still required; per-request production
authentication is not implemented. P1E-01 remains a reviewed proposal. Historical
freeze records and existing P1E draft files remain unchanged.

The owner prohibits commit/push/merge/deploy; changes remain uncommitted and the
historical clean-tree gate is not claimed satisfied. No profile, Gateway,
systemd, model/provider configuration or secrets are changed.
