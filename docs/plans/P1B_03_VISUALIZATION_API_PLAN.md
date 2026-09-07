# CostGuard Split P1B-03 Visualization API Implementation Plan v0.1


# Classification

P1B-03 = OPEN Visualization API Layer


This implementation exposes existing visualization projections only.


NOT AUTHORIZED:

- billing
- pricing engine
- quota management
- allocation intelligence
- optimization
- recommendation
- commercial intelligence



---

# Baseline


Release baseline:

v0.4.1-p1b02


Commit:

97144e6


Scope:

Post P1B-02 visualization DTO layer.



---

# Objective


Expose internal HTTP API endpoints for existing visualization DTOs.


The API layer:


- MUST be read only
- MUST NOT access database directly
- MUST NOT contain SQL
- MUST NOT modify analytics logic
- MUST preserve tenant isolation



---

# API Surface


Initial internal endpoints:


## GET /internal/visualization/summary


Purpose:

Return visualization summary cards.


Input:

- org_id
- start
- end


Output:

VisualizationSummaryDTO



---

## GET /internal/visualization/trend


Purpose:

Return daily usage trend.


Input:

- org_id
- start
- end
- interval=day


Output:

Trend DTO list



---

## GET /internal/visualization/providers


Purpose:

Return provider distribution.


Input:

- org_id
- start
- end


Output:

Provider distribution DTO



---

## GET /internal/visualization/models


Purpose:

Return model distribution.


Input:

- org_id
- start
- end


Output:

Model distribution DTO



---

# Architecture Boundary


Allowed:


HTTP router

    |

visualization API adapter

    |

visualization service

    |

analytics DTO



Forbidden:


HTTP router

    |

database



Router MUST NOT:

- execute SQL
- import database layer
- bypass visualization service



---

# Authentication and Authorization


Authentication mechanism:

Deferred.


Authorization boundary:

Mandatory.


Every request:

- MUST carry organization scope
- MUST enforce org isolation
- MUST hide cross-org access



---

# Storage Strategy


No migration.

No new tables.

No cache.

No materialized views.


This slice only exposes existing read projections.



---

# File Boundary


Allowed:


costguard_split/api/*

costguard_split/visualization/api_adapter.py

tests/split_p1b03_visualization_api_test.py



Forbidden:


costguard_split/ingest/*

costguard_split/connectors/*

costguard_split/identity/*

costguard_split/analytics/*

pricing logic



---

# Test Plan


Required:


| ID | Test |
|----|------|
| A1 | endpoint returns visualization DTO |
| A2 | router has no database dependency |
| A3 | provider endpoint works |
| A4 | model endpoint works |
| A5 | NULL cost preserved |
| A6 | no mutation |
| A7 | no private fields |
| A8 | no private intelligence |
| A9 | endpoint schema stability |
| A10 | invalid time range handling |
| A11 | organization isolation |
| A12 | no SQL in API layer |



---

# Coding Authorization


Current:

IMPLEMENTATION PLAN ONLY


Coding:

NOT AUTHORIZED


Requires:

- plan approval
- file boundary approval
- test approval


