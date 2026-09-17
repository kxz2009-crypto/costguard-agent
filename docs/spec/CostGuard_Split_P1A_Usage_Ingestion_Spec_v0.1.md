# CostGuard Split — P1A Usage Ingestion Engineering Spec v0.1

Version: v0.1
Status: Architecture / engineering baseline for implementation
Date: 2026-09-07
Applies to: CostGuard Split public foundation (OPEN CORE)
Baseline foundation: feature/split-p0-identity @ 6388f5fe9a19798cfa8241b88d7af460473cb2cc
Parent product baseline: main / v0.2.0-beta @ 66cca248925a098c809de50fb93185aedb50f8bc

## 0. Classification Gate (mandatory before coding)

```text
Feature: P1A Usage Ingestion Layer
Classification: OPEN
Reason: unified usage-event schema + connector interface + local collectors +
        token normalization + public pricing schema + idempotent ingest.
        No proprietary attribution, reconciliation, quota pressure,
        optimization, benchmark, or recommendation logic.
Public repo allowed: YES
Commercial risk: LOW (if boundaries below are enforced)
Server-side required: YES for organization, received_at, duplicate decision,
                      pricing_version, and any money computation
```

P1B remains NOT AUTHORIZED.

---

## 1. Objective

Build a unified AI Usage Event ingestion layer that:

1. lets collectors discover provider usage facts;
2. validates and normalizes them into a canonical event schema;
3. stores them with tenant isolation and idempotency;
4. prepares later public-price calculation without shipping commercial intelligence.

Supported provider trajectory (adapters, not core forks):

```text
claude
codex
openai
gemini
cursor
ollama / local
```

P1A MVP delivery focus:

```text
claude + codex first
adapter interface ready for the rest
```

---

## 2. Commercial Boundary (hard)

### 2.1 OPEN in P1A

Allowed:

- Usage Event Schema v1
- Connector Protocol / BaseConnector interface
- Local collectors for Claude / Codex (and later others)
- Token category normalization (incl. Claude cache tokens)
- Provider adapter plugins
- Idempotent ingest
- Validation / trust-boundary rejection
- Basic public pricing table schema
- Optional local API-equivalent estimate based on PUBLIC prices only
- Event-time member lookup via existing assignment timeline (`member_at`)

### 2.2 FORBIDDEN in P1A (must stay P1B / PRIVATE)

Must not enter public P1A code:

- automatic attribution / identity reconciliation
- device lineage intelligence
- proprietary confidence scoring / tuning
- quota pressure modeling
- reconciliation engine (subscription bill ↔ usage)
- optimization / routing / plan recommendation
- benchmark datasets or cohort construction
- commercial recommendation outcomes
- enterprise policy DSL / multi-stage allocation intelligence

If a ticket needs any of the above: STOP and reclassify.

---

## 3. Architecture Overview

```text
Collector (local)
  ClaudeConnector / CodexConnector / ...
        │
        │ UsageEventClaim (facts only)
        ▼
Ingest API / local ingest service
  validate whitelist
  reject forbidden authority/raw fields
  resolve organization from ServerContext
  resolve device by device_uid (tenant-safe)
  derive member_id via member_at(device, started_at)   # deterministic timeline only
  compute source_event_id if provider-native missing
  idempotent upsert
        │
        ▼
SQLite (P1A)  ──migration──▶  PostgreSQL (later)
  usage_events
  usage_token_buckets (or embedded token columns)
  public_pricing_versions (optional in P1A)
```

Reuse, do not reinvent:

- `costguard_split.schemas.dto.UsageEventClaim` (P0 contract seed)
- `canonical_source_event_id(provider, native_id)`
- assignment timeline + `member_at` (event-time attribution helper)
- numeric policy (no float money; tokens = int)
- audit append-only writer

---

## 4. UsageEvent Schema v1

### 4.1 Conceptual fields

```text
usage_events
------------
id                      TEXT PK                 # server mint: uev_<uuid>
organization_id         TEXT NOT NULL           # SERVER authority
device_id               TEXT NOT NULL           # SERVER resolved from device_uid
device_uid              TEXT NOT NULL           # client claim, validated
member_id               TEXT NULL               # SERVER derived (event-time)
provider                TEXT NOT NULL           # client claim (normalized)
provider_account_ref    TEXT NULL               # optional opaque ref (no secrets)
model                   TEXT NOT NULL
session_ref             TEXT NOT NULL           # client claim / collector-derived
source_event_id         TEXT NOT NULL           # normalized provider-native or derived
started_at              TEXT NOT NULL           # ISO8601 timezone-aware
ended_at                TEXT NOT NULL
received_at             TEXT NOT NULL           # SERVER clock
input_tokens            INTEGER NOT NULL DEFAULT 0
cached_input_tokens     INTEGER NOT NULL DEFAULT 0   # Claude cache read
cache_write_tokens      INTEGER NOT NULL DEFAULT 0
output_tokens           INTEGER NOT NULL DEFAULT 0
reasoning_tokens        INTEGER NOT NULL DEFAULT 0
request_count           INTEGER NOT NULL DEFAULT 1
pricing_version         TEXT NULL               # SERVER if priced
api_equivalent_cost_usd TEXT NULL               # SERVER Decimal as string / NUMERIC later
source_type             TEXT NOT NULL           # connector|import|manual
collector_version       TEXT NOT NULL DEFAULT ''
created_at              TEXT NOT NULL
```

Claude MUST support all five token categories. Input/output-only schemas are REJECTED.

### 4.2 Wire claim (collector → server)

Canonical claim = P0 `UsageEventClaim` extended with optional metadata that remains non-authoritative:

```text
REQUIRED CLAIM
--------------
device_uid
provider
source_event_id          # or omit only if connector can derive deterministically
model
started_at
ended_at
session_ref
input_tokens
cached_input_tokens
cache_write_tokens
output_tokens
reasoning_tokens
request_count

OPTIONAL CLAIM
--------------
provider_account_ref     # opaque, never a secret
collector_version
source_type              # default connector
```

### 4.3 Event identity

Primary identity for idempotency:

```text
(organization_id, device_uid, provider, source_event_id)
```

`source_event_id` rules:

1. Prefer provider-native unique id when available.
2. Else collector-derived deterministic id over a collision-resistant payload.
3. Normalize with `canonical_source_event_id(provider, native_id)` → `provider:native`.
4. NEVER use `(source, session_ref, timestamp)` alone — same-second multi-event collisions are real.

Recommended collector-derived formula when native id is absent:

```text
native = sha256_hex(
  provider | session_ref | started_at | ended_at | model |
  input | cached_input | cache_write | output | reasoning | request_count
)[:32]
source_event_id = canonical_source_event_id(provider, native)
```

Completely identical retransmit → same identity.
Different token payload → different identity.
Same provider/session/second with different tokens → different identity.

---

## 5. Trust Boundary

### 5.1 Collector MAY provide

```text
device_uid
provider
source_event_id (or materials to derive it)
session_ref
model
started_at / ended_at
token counters (ints)
request_count
provider_account_ref (opaque)
collector_version
```

### 5.2 Server MUST determine

```text
organization_id                 # from ServerContext / auth
device_id                       # lookup by device_uid inside org
member_id                       # member_at(device_id, started_at) only
received_at                     # server clock
duplicate decision              # unique key hit → idempotent return
pricing_version                 # if public pricing applied
api_equivalent_cost_usd         # if computed from PUBLIC price table
```

### 5.3 Never trust / never accept from client

Reject with 4xx (`extra=forbid` + explicit forbidden list):

```text
organization_id
member_id
identity_confidence
attribution_confidence
api_equivalent_cost / api_equivalent_cost_usd
price / cost / allocation / billing / estimated_cost
hostname / username / raw_ip / public_ip / local_ip
prompt / response / content
device.json wholesale dumps
arbitrary metadata blobs
```

Partial persist after rejection is forbidden (validate before write).

---

## 6. Idempotency & Ingest Semantics

### 6.1 Upsert behavior

```text
POST /api/v1/usage/events   (single)
POST /api/v1/usage/events:batch
```

For each claim:

1. validate schema / forbidden fields / token ints ≥ 0;
2. resolve org from context;
3. resolve device by `device_uid` within org (else 404 hidden);
4. compute/normalize `source_event_id`;
5. UNIQUE lookup on `(organization_id, device_uid, provider, source_event_id)`;
6. if exists → 200 + existing server event id (no mutation of immutable facts);
7. if new → insert with server `received_at`, derived `member_id`, optional public price.

Immutable after first accept:

```text
token counters
model
started_at / ended_at
session_ref
source_event_id
provider
```

Mutable (server-only, rare):

```text
pricing_version / api_equivalent_cost_usd   # if public price table version bumps and reprice job runs
```

Reprice jobs are OUT OF SCOPE for first P1A slice; schema must allow NULL money columns.

### 6.2 Batch rules

- max batch size: 500 events (P1A default)
- request body size limit: 1 MiB
- per-item results: created | duplicate | rejected
- one rejected item must not roll back accepted siblings (partial success OK with explicit result list)
- whole-request schema failure (malformed JSON / forbidden top-level keys) → 422, zero writes

### 6.3 Retry safety

Collectors may retry freely. Duplicates must be cheap and silent (200 duplicate), never create second rows.

---

## 7. Connector Architecture

### 7.1 Package layout (public)

```text
costguard_split/
  connectors/
    __init__.py
    base.py                 # BaseConnector ABC
    registry.py             # name → connector class
    claude.py               # OPEN
    codex.py                # OPEN
    openai.py               # optional follow-on
    gemini.py               # optional follow-on
    cursor.py               # optional follow-on
    ollama.py               # optional follow-on
  ingest/
    __init__.py
    service.py              # validate + upsert
    pricing_public.py       # optional public price apply
  schemas/
    usage.py                # UsageEventClaim (move/extend from dto.py)
```

### 7.2 BaseConnector contract

```text
class BaseConnector(ABC):
    name: str                       # provider key: claude|codex|...
    def discover(self, home: Path, since: datetime | None) -> Iterable[RawUsage]
    def normalize(self, raw: RawUsage) -> UsageEventClaim
    def native_event_id(self, raw: RawUsage) -> str | None
```

Rules:

- New provider = new module + registry entry. Core ingest service must not grow provider `if/elif` trees.
- Connectors never compute money.
- Connectors never assign members/orgs.
- Connectors never read prompts/responses into claims.
- Local raw provider logs stay LOCAL; only normalized claims leave the machine.

### 7.3 Claude / Codex specifics

Claude:

- map cache read → `cached_input_tokens`
- map cache write → `cache_write_tokens`
- reject connectors that drop cache classes

Codex:

- map available counters; missing classes → 0 (explicit), never omit columns

Both:

- produce timezone-aware `started_at` / `ended_at`
- provide `session_ref` (native or derived)
- prefer native event id; else deterministic hash formula in §4.3

---

## 8. Database Schema (P1A)

### 8.1 DDL sketch (SQLite now, PG-shaped)

```sql
CREATE TABLE usage_events (
  id                    TEXT PRIMARY KEY,
  organization_id       TEXT NOT NULL,
  device_id             TEXT NOT NULL,
  device_uid            TEXT NOT NULL,
  member_id             TEXT,
  provider              TEXT NOT NULL,
  provider_account_ref  TEXT,
  model                 TEXT NOT NULL,
  session_ref           TEXT NOT NULL,
  source_event_id       TEXT NOT NULL,
  started_at            TEXT NOT NULL,
  ended_at              TEXT NOT NULL,
  received_at           TEXT NOT NULL,
  input_tokens          INTEGER NOT NULL DEFAULT 0,
  cached_input_tokens   INTEGER NOT NULL DEFAULT 0,
  cache_write_tokens    INTEGER NOT NULL DEFAULT 0,
  output_tokens         INTEGER NOT NULL DEFAULT 0,
  reasoning_tokens      INTEGER NOT NULL DEFAULT 0,
  request_count         INTEGER NOT NULL DEFAULT 1,
  pricing_version       TEXT,
  api_equivalent_cost_usd TEXT,          -- Decimal string in SQLite; NUMERIC(12,4) in PG
  source_type           TEXT NOT NULL DEFAULT 'connector',
  collector_version     TEXT NOT NULL DEFAULT '',
  created_at            TEXT NOT NULL,
  UNIQUE (organization_id, id),
  UNIQUE (organization_id, device_uid, provider, source_event_id),
  FOREIGN KEY (organization_id, device_id)
    REFERENCES devices (organization_id, id),
  FOREIGN KEY (organization_id, member_id)
    REFERENCES members (organization_id, id),
  CHECK (input_tokens >= 0 AND cached_input_tokens >= 0 AND
         cache_write_tokens >= 0 AND output_tokens >= 0 AND
         reasoning_tokens >= 0 AND request_count >= 0)
);

CREATE INDEX idx_usage_org_time ON usage_events(organization_id, started_at);
CREATE INDEX idx_usage_device_time ON usage_events(device_id, started_at);
CREATE INDEX idx_usage_member_time ON usage_events(member_id, started_at);
```

Optional public pricing table (OPEN):

```sql
CREATE TABLE public_pricing_versions (
  version       TEXT PRIMARY KEY,
  effective_from TEXT NOT NULL,
  source        TEXT NOT NULL,          -- e.g. bundled|manual
  created_at    TEXT NOT NULL
);

CREATE TABLE public_model_prices (
  pricing_version TEXT NOT NULL,
  provider        TEXT NOT NULL,
  model           TEXT NOT NULL,
  input_per_mtok  TEXT NOT NULL,        -- Decimal string
  output_per_mtok TEXT NOT NULL,
  cache_read_per_mtok  TEXT,           -- NULL if N/A
  cache_write_per_mtok TEXT,
  reasoning_per_mtok   TEXT,
  PRIMARY KEY (pricing_version, provider, model)
);
```

Money policy: Decimal / TEXT-encoded Decimal in SQLite; NUMERIC(12,4)+ in PostgreSQL. REAL/FLOAT/DOUBLE forbidden.

### 8.2 Why not a separate usage_tokens table in P1A

P1A keeps token classes as columns on `usage_events` for:

- simpler idempotent upserts;
- cheaper reporting sums;
- Claude cache classes always present.

A vertical `usage_token_buckets` table is deferred unless a provider requires unbounded custom classes. Extension path: nullable JSON `token_extras` is REJECTED for P1A (invites float/opaque junk). Prefer explicit columns.

### 8.3 Member attribution in P1A

`member_id` is DERIVED at ingest via:

```text
member_at(device_id, at=started_at)
```

This is deterministic timeline lookup (OPEN). It is NOT automatic identity intelligence (PRIVATE).

If unassigned at event time → `member_id IS NULL` (derived unassigned). Never invent a member.

---

## 9. Pricing Boundary

### 9.1 P1A allowed

- Store token facts without money.
- Optionally apply PUBLIC bundled price table → `api_equivalent_cost_usd`.
- Persist `pricing_version` used.
- Document that local estimates are approximate.

### 9.2 P1A forbidden

- Subscription pool reconciliation
- Enterprise discount / private contract prices
- Quota pressure weights
- “true internal cost” intelligence
- Learned price adjustments

### 9.3 Decision for first implementation slice

```text
Slice P1A-1: ingest + schema + connectors + idempotency (money columns NULL)
Slice P1A-2: optional public price apply (explicitly gated feature flag)
```

Do not block P1A-1 on pricing.

---

## 10. API Surface (P1A)

```text
POST /api/v1/usage/events
POST /api/v1/usage/events:batch
GET  /api/v1/usage/events/{id}
GET  /api/v1/usage/events?from=&to=&device_id=&member_id=&provider=
```

All routes:

- org from ServerContext
- foreign ids → 404 hidden
- forbidden fields → 422
- conflicts / duplicates → 200 duplicate (not 409) for idempotent retransmit
- unexpected → 500 without traceback

Healthz unchanged (minimal).

Auth remains process-level ServerContext in P1A staging; real auth is a separate production gate (already recorded debt).

---

## 11. Migration Strategy

### 11.1 Versioning

Continue `schema_version` table:

```text
v1..v2   P0 identity / assignments
v3       P1A usage_events (+ optional public pricing tables)
```

`apply_migrations` remains idempotent. Fresh DB jumps to latest.

### 11.2 SQLite → PostgreSQL

Preserve shapes:

| SQLite | PostgreSQL |
|---|---|
| TEXT ids | TEXT/UUID |
| TEXT timestamps | TIMESTAMPTZ |
| INTEGER tokens | BIGINT |
| TEXT decimal money | NUMERIC(12,4) |
| UNIQUE(...) | UNIQUE + optional EXCLUDE later |

Composite FKs already established in P0 must be preserved for `usage_events`.

### 11.3 Backfill

No Agent → Split automatic backfill in P1A core. Optional offline import tool may convert Agent exports into UsageEventClaims with the same trust boundary.

---

## 12. Testing Matrix

| ID | Case | Type | Gate |
|---|---|---|---|
| U1 | UsageEventClaim rejects float tokens | UNIT | P1A |
| U2 | Forbidden authority fields rejected | UNIT/CONTRACT | P1A |
| U3 | Claude cache token classes round-trip | UNIT | P1A |
| U4 | canonical_source_event_id stable + distinct | UNIT | P1A |
| U5 | same-second different payloads → different ids | UNIT | P1A |
| I1 | first ingest 201/created | INTEGRATION | P1A |
| I2 | identical retransmit 200/duplicate, same server id | INTEGRATION | P1A |
| I3 | batch partial success | INTEGRATION | P1A |
| I4 | event-time member_at derivation | INTEGRATION | P1A |
| I5 | unassigned device → member_id NULL | INTEGRATION | P1A |
| S1 | spoof cost/org/member → 422 + zero rows | SECURITY | P1A |
| S2 | cross-org device_uid event → 404/reject, no leak | SECURITY | P1A |
| S3 | foreign event GET → 404 | SECURITY | P1A |
| C1 | ClaudeConnector normalize fixture | CONTRACT | P1A |
| C2 | CodexConnector normalize fixture | CONTRACT | P1A |
| C3 | adding FakeProvider requires no core edit | CONTRACT | P1A |
| M1 | migration v2→v3 idempotent | INTEGRATION | P1A |
| M2 | fresh DB → v3 | INTEGRATION | P1A |
| P1 | public price apply optional path Decimal-safe | UNIT | P1A-2 |
| X1 | no REAL/FLOAT money columns guard | UNIT | continuous |

All tests use temporary COSTGUARD_HOME / tmp DB. No host `~/.costguard` dependence.

Agent legacy host-data tests remain parent debt and must not gate P1A.

---

## 13. Security & Privacy

- No prompts/responses/content in claims, DB, audits, or logs.
- No raw hostname/username/IP in usage payloads.
- Device evidence remains fingerprint-only.
- Audit events for ingest: `usage.ingested`, `usage.duplicate`, `usage.rejected` (org-scoped, structured JSON).
- Rate limit / body size limits required before public internet exposure (staging may use controlled network first).

---

## 14. Implementation Ticket Order

```text
P1A-01  Schema v3 migration + usage_events DDL + numeric guards
P1A-02  UsageEventClaim finalize (API pydantic model, extra=forbid)
P1A-03  Ingest service (single + batch) + idempotency
P1A-04  BaseConnector + registry
P1A-05  ClaudeConnector
P1A-06  CodexConnector
P1A-07  HTTP routes under /api/v1/usage/*
P1A-08  Test matrix U*/I*/S*/C*/M*
P1A-09  Optional public pricing apply (feature-flagged)
P1A-10  Docs + classification checklist on every PR
```

Do not start P1B tickets from this list.

---

## 15. Definition of Done (P1A)

P1A is DONE when:

1. Claude and Codex usage can be normalized into UsageEvent Schema v1 with all token classes;
2. ingest is idempotent under retry and same-second multi-event cases;
3. trust boundary rejects cost/org/member spoofing with zero partial writes;
4. tenant isolation holds for insert and read;
5. member_id is derived only from assignment timeline (or NULL);
6. connectors are registry-pluggable without core edits;
7. migrations are versioned and idempotent;
8. public pricing (if enabled) uses Decimal and public tables only;
9. commercial-boundary PR checklist passes;
10. split suites green on clean machines (no host-data dependence).

---

## 16. What is public vs private

### Public (this repo / OPEN)

- Everything in §§3–14 except where marked optional private ops.
- Claude/Codex local collectors.
- Public price tables.
- Ingest API + validation.
- Deterministic event-time assignment lookup.

### Private / later (P1B+)

- Automatic attribution beyond timeline lookup
- Lineage / merge / reinstall intelligence
- Proprietary confidence models
- Quota pressure
- Bill reconciliation
- Optimization / recommendations
- Benchmark datasets
- Enterprise private pricing

---

## 17. P1A READY verdict

**P1A READY**

Ready to implement against this spec, starting at P1A-01, under OPEN classification.

Not ready / not authorized:

- P1B commercial intelligence
- production internet exposure without auth + rate limits
- treating public API-equivalent cost as “true internal cost”

### Re-review trigger

After P1A-01..P1A-08 land on the feature branch, run an independent API/ingest review before enabling staging traffic that accepts external collector uploads. Focus: trust boundary, idempotency collisions, tenant isolation, connector isolation, and commercial-boundary scan.

---

## 18. Unverified / deferred notes

- Exact Claude/Codex local file formats must be confirmed against current provider artifacts during connector implementation (fixtures required; no live customer logs in repo).
- PostgreSQL runtime not exercised in this design pass.
- Real auth token model deferred (existing P0 debt).
- Sessionization heuristics beyond provided `session_ref` are optional and must remain deterministic/OPEN if added; behavioral session intelligence is P1B.
