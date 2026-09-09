# CostGuard Split P1D-04 Open Consumption API Gate v1.0 (AMENDED PER CODEX REVIEW)


REVIEW STATUS:

Amended per Codex review record:
docs/gates/reviews/P1D_04_GATE_DRAFT_CODEX_REVIEW.md

All seven amendments (1-7) are incorporated.

This gate authorizes the DESIGN only.

Coding remains NOT AUTHORIZED until:

- implementation plan written and approved
- file boundary approved
- test plan approved
- user sign-off recorded
- DECISIONS.md question resolved (see Amendment 7 / section
  "Authorization Status")


# Classification

P1D-04 = OPEN Open Consumption API (DESIGN AUTHORIZED, CODING PENDING)

If separately authorized for implementation, this gate permits HTTP
consumption of existing analytics and visualization projections, the
P1C-01 time-series read model, and the three P1D read layers: export,
dashboard, and report. P1C-02 supplies the existing trend HTTP adapter.

This gate does NOT authorize:

- billing
- pricing engine
- quota management
- allocation intelligence
- optimization
- recommendation
- commercial intelligence
- public internet exposure
- API keys / tokens / auth systems
- rate limiting (deferred; see Rate Limiting / Caching)


# Baseline

Release baseline:

v0.7.0-p1d03

Tag:

v0.7.0-p1d03

Commit:

d161f8c

Scope:

Post P1D-03 report generation.


# Objective

Expose existing read models through a stable internal consumption
API with explicit versioning, so downstream consumers (dashboard
frontend, report tooling, future SaaS surface) can integrate
without coupling to internal module structure.

API MUST:

- be read only
- expose only existing read models (no new aggregation)
- preserve analytics boundary
- avoid direct database access in the API layer
- avoid business decisions
- return deterministic payload shapes


# Relationship to P1B-03 (PREVIOUS internal API)

The P1B-03 gate specified /internal/visualization/*; the
implementation exposes /api/v1/visualization/*, including the
trend route subsequently added by P1C-02. Preserve all
implemented visualization routes and their contracts unchanged.
Add /api/v1/consumption/* without aliases, replacement, or
deprecation in this slice.

(The precedent gate explicitly deferred the trend endpoint
pending a time-series read model: P1B_03 gate line 298. That
read model now exists via P1C-01; this gate adds no new
time-series aggregation.)


# Allowed Capability

OPEN (proposed endpoints, all read-only):

## GET /api/v1/consumption/summary

Input (query):

- org_id (required)
- start (required)
- end (required)
- provider, model, member_id, device_id (optional filters)

Return: analytics summary DTO serialization (asdict shape of
AnalyticsSummary: totals + by_provider/by_model/by_member/
by_device dimension lists)


## GET /api/v1/consumption/timeseries

Input (query):

- org_id, start, end (required)
- granularity=day|hour (required)

Return: list of TimeSeriesPoint serializations (point order
preserved)


## GET /api/v1/consumption/distributions

Input: same as summary

Return: exactly provider_distribution and model_distribution,
each containing serialized DistributionPoint objects with
dimension, key, events, tokens


## GET /api/v1/consumption/dashboard

Required query parameters:

- org_id, start, end, granularity=day|hour

Dashboard filters are NOT supported in this slice. Requests
containing provider, model, member_id, or device_id return 422;
they MUST NOT be silently ignored. The adapter calls
dashboard_projection() without filters. Filtered dashboard
trends require a separately authorized read-model change.

Return: DashboardPayload.to_dict() — meta, totals,
provider_distribution, model_distribution, trend, extra


## GET /api/v1/consumption/export/summary | /export/timeseries |
/export/distributions

Input: same as corresponding section

Return: complete ExportDocument.to_dict() (manifest with
content_hash + payload), including the distribution payload's
summary block


## GET /api/v1/consumption/report/summary | /report/timeseries

Input: corresponding inputs

Return: complete ReportDocument.to_dict() (meta + content_hash +
markdown body string). No file download or HTML rendering.


## Health

No additional health endpoint is introduced. Existing /healthz
remains unchanged.


NOT OPEN (rejected from this slice):

- POST/PUT/DELETE anywhere on this namespace
- pagination (see Time Window Policy)
- field selection / sparse responses
- compression negotiation
- batch/multi-org endpoints
- OpenAPI document customization (FastAPI default schema stays)


# Architecture Boundary


Allowed:

HTTP
 |
 v
/api/v1/consumption router (new module)
 |
 v
existing services: analytics / timeseries / visualization /
export / dashboard / report
 |
 v
existing DTOs


Forbidden:

HTTP
 |
 v
database

No direct SQL inside the API layer.
No import of costguard_split.db or sqlite3 in the router module.


# Versioning Contract

The v1 stability commitment applies only to
/api/v1/consumption/*. It covers field names, types, nullability,
query semantics, ordering semantics, and documented errors.
Internal DTO changes do not automatically authorize wire-contract
changes. Preserve existing document schema versions, baseline
metadata, hash algorithms, and hash inputs. Success-shape
requirements do not replace documented error bodies.

- breaking changes require a new namespace, never in-place mutation
- every response carries no wrapper beyond the documented shape


# Tenant Isolation Boundary

Authentication mechanism may be deferred.

Authorization boundary MUST NOT be deferred.

Every consumption data endpoint:

- requires an explicit org_id and a non-null, server-supplied
  ServerContext
- missing context or an org_id mismatch returns 404 with
  {"detail": "not found"} BEFORE calling any read service
- client query parameters, bodies, and headers MUST NOT create
  or select the authoritative context

Note: this deliberately differs from the legacy _check_org
pattern in api/visualization.py and api/trend_visualization.py,
which bypasses the check when context is None and create_app()
defaults to None. The stricter rule applies ONLY to consumption
routes; legacy routes are untouched.


# Error Contract

- missing server context or requested organization differing
  from the context returns 404; a matching context organization
  with no matching usage returns the existing empty read-model
  representation; no organization-existence database lookup is
  introduced
- missing required query param -> 422 (FastAPI default)
- unsupported granularity -> 400 (explicit check in router,
  validated BEFORE service invocation, including for empty
  datasets)
- unsupported/forbidden dashboard filters -> 422
- no other error surface changes


# Time Window Policy

- start and end must be timezone-aware ISO-8601 timestamps
- normalize them to the ingestion UTC serialization before
  calling services
- the window is [start, end) and must satisfy start < end and a
  maximum duration of 31 days (PROPOSED GATE DECISION, not an
  existing code constraint)
- malformed, timezone-naive, reversed, empty, or oversized
  windows return 400
- missing required parameters return 422


# Pagination

Pagination is deferred for the initial internal surface. The
window limit does not bound event or dimension cardinality, and
existing services materialize matching events (fetchall).
Responses are complete, without silent truncation. Public or
larger-scale operational exposure requires a separate
resource-control review.


# Rate Limiting / Caching

Every response under /api/v1/consumption/ MUST carry
Cache-Control: no-store, including validation and error
responses (framework-generated ones included). Rate limiting,
application caching, ETags, and conditional responses remain
deferred.


# Storage Policy

No new tables.

No migration.

No cache.

No materialized views.


# File Boundary

Allowed additions:

- costguard_split/api/consumption.py
- tests/split_p1d04_consumption_api_test.py

Allowed modifications:

- costguard_split/api/app.py: importing and invoking the
  consumption adapter's registration function before
  include_router() only. Any namespace-scoped response policy is
  implemented in consumption.py and installed by that function;
  it must not change existing routes' behavior.

Forbidden:

- costguard_split/ingest/*
- costguard_split/connectors/*
- costguard_split/identity/*
- costguard_split/analytics/* (read-only consumption)
- costguard_split/visualization/*, export/*, dashboard/*, report/*
  (consumed, never modified)
- pricing logic
- new dependencies


# Response Contract

All successful consumption responses are JSON. Shapes are the
documented to_dict() serializations of the existing DTOs:

- /summary: AnalyticsSummary asdict (totals + by_* lists)
- /timeseries: list of TimeSeriesPoint asdicts, source order
- /distributions: exactly provider_distribution and
  model_distribution lists of DistributionPoint asdicts
- /dashboard: meta, totals, provider_distribution,
  model_distribution, trend, extra
- /export/*: complete ExportDocument.to_dict()
- /report/*: complete ReportDocument.to_dict(); report cost
  nulls render as empty Markdown cells inside the body string
  (not JSON nulls)


# Scope Clarification

"External consumption" means consumers outside the Python
modules; this slice remains internally deployed. It does not
authorize public internet availability or a SaaS service
commitment.

Versioning and a stable consumption contract are within roadmap
scope (CostGuard_Split_ROADMAP_v0.1.md line 265, "Stable external
consumption interface", "Requires separate API gate").

Explicitly OUT of scope: extending stability to the entire
/api/v1 namespace, replacing legacy routes, or adding filtered
time-series aggregation.


# Required Tests

| ID | Requirement |
|----|-------------|
| K1 | summary endpoint returns analytics summary shape |
| K2 | timeseries endpoint preserves point order |
| K3 | distributions endpoint matches visualization output |
| K4 | dashboard endpoint matches DashboardPayload.to_dict() |
| K5 | export endpoints carry manifest + content_hash |
| K6 | report endpoints carry markdown body + content_hash |
| K7 | no database access from router (module boundary) |
| K8 | NULL cost preserved per existing representation |
| K9 | no mutation: row counts AND row contents stable |
| K10 | no private fields / no raw request bodies |
| K11 | explicit baseline response keys/types/nullability |
| K12 | defined time-validation outcomes (malformed, naive, reversed, oversized -> 400) |
| K13 | organization isolation across EVERY data endpoint (foreign org -> 404, no leak) |
| K14 | router has no SQL dependency |
| K15 | invalid granularity -> 400 with empty AND populated data |
| K16 | missing required params -> 422 |
| K17 | P1B-03 routes untouched; both visualization API and trend API regression suites pass |
| K18 | Cache-Control: no-store on success AND error responses |
| K19 | missing server context -> 404 before any service call |
| K20 | dashboard filter params -> 422 |
| K21 | service-output parity (endpoint response equals direct service call) |
| K22 | export/report hashes unchanged across repeated renders |


# Authorization Status

Current:

DESIGN AUTHORIZED (post-amendment), CODING NOT AUTHORIZED

Requires before coding:

- implementation plan written and approved
- file boundary approval (granted in this gate for
  consumption.py + app.py registration hook, contingent on plan)
- test plan approval (K1-K22 constitute the plan; contingent on
  plan approval)
- identify the authoritative CostGuard DECISIONS.md and reconcile
  this gate with its applicable conventions, OR explicitly
  record that no such document applies. Current finding: no
  DECISIONS.md exists in costguard-core/ or the costguard/
  umbrella directory; the authoritative conventions documents
  are the gates, plans, and spec under docs/. This finding must
  be confirmed or corrected at plan approval.
- user sign-off (this gate is explicitly user-escalation-worthy)
