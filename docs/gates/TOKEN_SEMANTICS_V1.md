# Additive token semantics v1

The local real Hermes trial exposed a source semantics mismatch: legacy generic
report totals sum reasoning again, while Hermes CanonicalUsage.total_tokens sums
input + cache read + cache write + output. Keep source counters and all existing
routes intact. Add GET /api/v1/consumption/token-semantics with the same org_id,
start, end, provider, model, member_id, device_id filters and tenant/window guards.

The response schema_version is 1; basis is declared-collector-version. Only
hermes-cumulative-v1 currently maps to hermes-canonical-v1. Reasoning remains
visible in each group's raw fields but is not added to its token_total_nullable.
Unknown versions, including blank/null and unimplemented Claude/Codex versions,
return null totals. A mixture containing any unknown-source event has a null
aggregate total and an explicit unknown_semantics_events count. The empty set
has zero events and zero total. No cost calculations, migration or event edits.

A collector version is client-supplied metadata, not authenticated provenance,
verified provider billing, or proof that the client applied normalization.
Do not infer semantics from provider/model names. The API's basis label is part
of the contract and consumers should show it. Group counters preserve source
values; unlike the comparable total they remain available for unknown groups.

Legacy /report/summary and other consumers retain their historical field-sum
behavior. Consumers requiring Hermes-native totals must opt into this endpoint;
this change does not silently correct every existing dashboard. Future source
mappings need normalization evidence and mixed-source regression tests. Pricing
accuracy and production deployment remain outside this change.

Acceptance: native Hermes total with cached input/write preserved, separate
reasoning detail, unknown/mixed/empty results, recognized version only, tenant
and window restrictions, parameterized filters, no-store, read-only database,
and unchanged legacy report body/hash.

## Authorized token-analysis read model

The same additive, non-commercial read-only scope authorizes
`GET /api/v1/consumption/token-analysis`. Its purpose is to project one filtered
snapshot into comparable token summaries by provider/model pair and UTC calendar
day without changing stored events or inventing per-call timing. It accepts the
same required `org_id`, `start`, and `end` parameters and optional `provider`,
`model`, `member_id`, and `device_id` filters as token-semantics. The server-bound
organization must match, the normalized half-open UTC window is `[start, end)`,
and the existing positive, timezone-aware, maximum-31-day window guard applies.
All filters remain parameterized.

The response contract is:

- `schema_version`: string `"1"`;
- `window`: the normalized UTC `start` and `end` strings used by the query;
- `day_basis`: string `utc-observation-start`;
- `cross_day_events`: number of selected events whose UTC start and end dates
  differ;
- `summary`: exactly the token-semantics v1 summary for all selected rows;
- `models`: one token-semantics v1 summary per distinct stored `(provider,
  model)` pair, augmented with those nullable stored identity fields, ordered by
  descending `request_count` and then provider/model with null sorting as empty;
- `days`: one entry for every UTC date touched by the normalized window's day
  iteration, each containing `date` plus the token-semantics v1 summary for rows
  attributed to that date. A partial window can therefore name both boundary
  dates. Empty day summaries have zero events, requests, and total.

Events are selected solely by `started_at >= start AND started_at < end`. Each
event is assigned in full to the UTC date of `started_at`; a cumulative
observation spanning dates increments `cross_day_events` but is never apportioned
or presented as reconstructed daily API calls. Model analysis groups by the
stored provider/model pair rather than inferring either identity. Null provider
or model values remain null and form their own pair; no `unknown` label is
substituted for identity. Token comparability is still governed only by declared
collector version: blank, null, and unrecognized versions retain raw counters,
use `semantics: unknown`, increment `unknown_semantics_events`, and make their
containing group's `token_total_nullable` null. Any such event makes the overall
summary null; recognized and empty groups follow the token-semantics rules above.

This surface reads only the selected usage-event facts and returns `no-store`.
It performs no writes, source-event edits, cost or pricing calculation, billing
verification, timing reconstruction, recommendations, intelligence, commercial
workflow, transport, scheduling, authentication expansion, or new public
exposure beyond this route in the already authorized consumption namespace.
Collector-version labels remain client declarations, not trusted provenance.
Legacy reports and their hashes remain unchanged.

Acceptance additionally requires exact start-time day attribution including a
cross-day event, distinct provider/model-pair grouping, mixed known/unknown and
empty-day behavior, null/unknown preservation, tenant rejection, normalized
window enforcement, parameterized filters, read-only storage, `no-store`, and
equality between `summary` and token-semantics for the same request.
