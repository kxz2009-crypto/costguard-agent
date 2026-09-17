# CostGuard Split P1B-01 Usage Analytics Read Model Implementation Plan v0.1

## Classification

P1B-01 = OPEN Analytics Layer

This implementation does NOT authorize PRIVATE commercial intelligence.

NOT AUTHORIZED:

- enterprise contract pricing
- billing reconciliation
- quota management
- allocation intelligence
- optimization engine
- recommendation engine
- learned intelligence


---

# Baseline

Release baseline:

v0.3.0-p1a

Commit:

9ba79d3d1dba80f5d81163028c816145c25588a8


Current planning branch:

1e4296e / later tip containing P1B gate documents


---

# Objective

Build a read-only analytics service derived from immutable usage facts.

Source of truth:

usage_events


The analytics layer:

- MUST NOT mutate usage_events
- MUST NOT change ingest behavior
- MUST NOT recalculate public pricing
- MUST NOT introduce private intelligence


---

# Scope

Allowed:

- usage aggregation
- provider summary
- model summary
- token statistics
- time-window reports
- read-only analytics DTO


Not included:

- HTTP API exposure
- dashboard UI
- billing logic
- recommendation
- optimization


---

# Query Contract

Initial implementation provides internal service-level query only.

No public HTTP route in this slice.


Example:

analytics_summary(
    org_id,
    start,
    end,
    provider=None,
    model=None,
    member_id=None,
    device_id=None
)


Return DTO:


{
totals: {
events,
request_count,
input_tokens,
cached_input_tokens,
cache_write_tokens,
output_tokens,
reasoning_tokens,
public_cost_sum_nullable
},

by_provider: [],
by_model: [],
by_member: [],
by_device: []
}



---

# Time Semantics

All filtering uses:

started_at


Rules:

- UTC only
- half-open interval [start, end)
- received_at is ingestion metadata only


Late events:

included according to started_at.


---

# Money Policy

api_equivalent_cost_usd:

Allowed:

- read existing stored public estimate


Forbidden:

- recalculation
- repricing
- filling NULL values


NULL remains NULL.


---

# Storage Strategy

Initial implementation:

NO migration.

NO new tables.

NO materialized views.

NO cache.


Read directly from:

usage_events


Future storage optimization requires separate gate.


---

# File Boundary

## Allowed additions


costguard_split/analytics/*
tests/split_p1a_analytics_test.py



## Forbidden modifications


costguard_split/ingest/service.py
costguard_split/connectors/*
costguard_split/identity/*
costguard_split/services/device_registry.py
pricing apply logic
usage_events write path
claim boundary schemas



---

# Test Plan

Required cases:

| ID | Test |
|----|------|
| A1 | aggregation correctness |
| A2 | half-open time boundary |
| A3 | started_at filtering semantics |
| A4 | NULL member grouping |
| A5 | NULL money handling |
| A6 | organization isolation |
| A7 | usage_events immutable |
| A8 | no raw content exposure |
| A9 | no PRIVATE intelligence symbols |


---

# Authorization Status

Current:

IMPLEMENTATION PLAN ONLY


Coding authorization:

NOT GRANTED


Required before coding:

- plan review approval
- file boundary approval
- test matrix approval


---

# Future Gates

Separate review required for:

- recommendation
- optimization
- commercial intelligence
