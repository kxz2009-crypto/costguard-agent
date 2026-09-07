# CostGuard Split P1B-03 Visualization API Gate v0.1


# Classification

P1B-03 = OPEN Visualization API Layer

This gate authorizes HTTP exposure of existing visualization DTOs only.

This gate does NOT authorize:

- billing
- pricing engine
- quota management
- allocation intelligence
- optimization
- recommendation
- commercial intelligence


# Baseline

Release baseline:

v0.4.1-p1b02

Tag:

v0.4.1-p1b02


Commit:

97144e6


Scope:

Post P1B-02 visualization read model.


# Objective

Expose visualization DTOs through internal HTTP API.

API MUST:

- be read only
- expose existing visualization projections
- preserve analytics boundary
- avoid direct database access
- avoid business decisions


# Allowed Capability

OPEN:

- usage trend endpoint
- provider distribution endpoint
- model distribution endpoint
- visualization summary endpoint


# API Boundary


Allowed:

HTTP
 |
 v
API router
 |
 v
visualization service
 |
 v
analytics DTO


Forbidden:

HTTP
 |
 v
database


No direct SQL inside API layer.




# Endpoint Contract


Initial internal API surface:


## GET /internal/visualization/summary


Input:

- org_id
- start
- end


Return:

VisualizationSummaryDTO



## GET /internal/visualization/trend


Input:

- org_id
- start
- end
- interval=day


Return:


[
 {
   date,
   events,
   tokens,
   public_cost_nullable
 }
]



## GET /internal/visualization/providers


Input:

- org_id
- start
- end


Return:


[
 {
   provider,
   events,
   tokens
 }
]



## GET /internal/visualization/models


Input:

- org_id
- start
- end


Return:


[
 {
   model,
   events,
   tokens
 }
]




# Tenant Isolation Boundary


Authentication mechanism may be deferred.

Authorization boundary MUST NOT be deferred.


Every endpoint:

- MUST require organization scope
- MUST only expose requested organization data
- MUST hide cross-organization access as 404 or equivalent


# Storage Policy

No new tables.

No migration.

No cache.

No materialized views.


# Authentication Boundary

Initial implementation:

internal API only.


Authentication implementation is deferred.

No public SaaS exposure.


# File Boundary


Allowed additions:

costguard_split/api/*
costguard_split/visualization/api_adapter.py
tests/split_p1b03_visualization_api_test.py


Forbidden:

costguard_split/ingest/*
costguard_split/connectors/*
costguard_split/identity/*
costguard_split/analytics/*
pricing logic




# Public API Exclusions


Not included in this slice:


- public API documentation
- external SDK
- SaaS API commitment
- backward compatibility guarantee


# Required Tests


| ID | Requirement |
|----|-------------|
| A1 | endpoint returns visualization DTO |
| A2 | no database access from router |
| A3 | provider distribution works |
| A4 | model distribution works |
| A5 | NULL cost preserved |
| A6 | no mutation |
| A7 | no private fields |
| A8 | no private intelligence symbols |
| A9 | endpoint schema stability |
| A10 | invalid time range handling |
| A11 | organization isolation |
| A12 | router has no SQL dependency |


# Authorization Status

Current:

READ GATE ONLY


Coding:

NOT AUTHORIZED


Requires:

- implementation plan
- file boundary approval
- test plan approval
