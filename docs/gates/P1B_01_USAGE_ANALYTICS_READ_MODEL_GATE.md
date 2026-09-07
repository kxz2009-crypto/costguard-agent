# CostGuard Split P1B-01 Usage Analytics Read Model Gate v0.3

## Gate Classification

P1B-01 is classified as:

OPEN Analytics Layer

This gate does NOT authorize PRIVATE commercial intelligence.

PRIVATE capabilities remain NOT AUTHORIZED:

- enterprise contract pricing
- billing reconciliation
- quota management
- allocation intelligence
- optimization engine
- recommendation engine
- learned intelligence


---

# Baseline

## Reference

P1A release tag:

v0.3.0-p1a

Commit:

9ba79d3d1dba80f5d81163028c816145c25588a8


Current review branch:

1e4296e


Review scope:

Post P1A usage foundation and optional public pricing.


---

# Objective

Introduce a read-only analytics layer derived from immutable usage facts.

Source of truth:

usage_events


Analytics layer MUST NOT mutate usage facts.


---

# Allowed Capability

OPEN:

- usage aggregation
- provider summary
- model summary
- token statistics
- time-window reports
- read-only dashboards


---

# Data Dimensions

Supported aggregation dimensions:

- organization
- member
- device
- provider
- model
- calendar time


---

# Time Semantics

All analytics queries use event time.

Primary timestamp:

started_at

received_at is ingestion metadata only.

Interval:

[start, end)

Timezone:

UTC only.

Late arriving events:

Analytics must include events based on started_at.

No mutation of usage_events is allowed.


---

# Money Policy

api_equivalent_cost_usd:

Allowed:

- read existing stored public estimation values


Forbidden:

- recompute pricing in analytics path
- apply new price tables
- modify historical cost values


NULL handling:

- NULL money remains NULL
- NULL member_id remains NULL
- missing facts must not be fabricated


---

# Query Contract

P1B-01 exposes an internal analytics service contract only.

No public HTTP route is authorized in this slice.

Example service interface:

```text
summary(
    org_id,
    start,
    end,
    provider=None,
    model=None,
    member_id=None,
    device_id=None
)
```

Returns:

```json
{
  "totals": {
      "events": 0,
      "tokens": {
          "input": 0,
          "cached_input": 0,
          "cache_write": 0,
          "output": 0,
          "reasoning": 0
      },
      "request_count": 0,
      "public_cost_sum": null
  },

  "by_provider": [],
  "by_model": [],
  "by_member": [],
  "by_device": []
}
```

Ordering:

- events DESC
- tokens DESC
- public_cost DESC

Pagination:

Not required in first implementation.

If added later:
separate gate required.

External HTTP API exposure requires separate review.


---

# Data Exposure Policy

usage_events remains the source of truth.

P1B-01 provides aggregated facts only.

Direct raw usage_events export is NOT included.

The analytics layer MUST NOT expose:

- prompts
- responses
- source transcript content
- local file paths
- secrets


---

# Storage Strategy

Default implementation:

NO migration.

NO materialized tables.

NO cache.

Analytics reads directly from usage_events.

Future:

Materialized views or cache require:

- separate gate
- migration review
- invalidation strategy


---

# Security Boundary

All reads MUST be organization scoped.

Required:

- ServerContext tenant boundary
- cross organization IDs hidden
- no raw prompts
- no raw responses
- no source transcript paths
- no secrets


Network dependency:

NOT REQUIRED.


---

# Implementation Boundary

Allowed:

Add:

```text
costguard_split/analytics/*
tests/split_p1a_analytics_test.py
```

Forbidden:

Modify:

```text
costguard_split/ingest/service.py
costguard_split/connectors/*
costguard_split/identity/*
costguard_split/services/device_registry.py
pricing apply logic
claim boundary schemas
usage_events write path
```

No P1B private intelligence.


---

# Required Test Matrix

Required before implementation acceptance:


| ID | Requirement |
|----|-------------|
| A1 | aggregation correctness |
| A2 | time boundary correctness |
| A3 | started_at semantics |
| A4 | NULL member handling |
| A5 | NULL money handling |
| A6 | organization isolation |
| A7 | no mutation of usage_events |
| A8 | no raw content exposure |
| A9 | no PRIVATE intelligence symbols |


---

# Authorization Status

Current:

READ GATE ONLY


Coding:

NOT AUTHORIZED


Authorization requires:

- gate approval
- implementation plan review
- file boundary approval
- test plan approval


---

# Separate Future Gates

Not included:

- recommendation features
- optimization
- commercial intelligence

Those require independent gates.
