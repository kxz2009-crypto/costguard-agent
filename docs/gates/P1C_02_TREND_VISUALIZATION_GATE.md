# CostGuard Split P1C-02 Trend Visualization Gate v0.1


# Classification

P1C-02 = OPEN Trend Visualization Layer


This gate exposes existing time-series analytics projections only.


NOT AUTHORIZED:

- billing
- pricing logic
- quota management
- allocation intelligence
- optimization
- recommendation
- forecasting
- anomaly detection



# Baseline


Release baseline:

v0.5.0-p1c01


Commit:

Current P1C-01 completion baseline.


Scope:

Post P1C-01 time-series analytics read model.



# Objective


Expose existing TimeSeries analytics projections through visualization layer.


The implementation MUST:


- consume existing TimeSeries DTO
- remain read only
- preserve analytics boundary
- avoid direct database access
- avoid duplicate aggregation logic
- avoid business decisions



# Architecture Boundary


Allowed:


HTTP

 |

visualization API adapter

 |

timeseries analytics service

 |

TimeSeries DTO



Forbidden:


HTTP

 |

usage_events database



Rules:


Visualization layer MUST NOT:

- execute SQL
- access usage_events directly
- perform GROUP BY aggregation
- calculate cost
- generate predictions



# Allowed Capability


OPEN:


- daily trend endpoint
- hourly trend endpoint


NOT INCLUDED:


- forecasting
- anomaly detection
- alerts
- recommendations
- optimization



# Endpoint Contract


Initial internal API:


## GET /internal/visualization/trend


Input:


- org_id
- start
- end
- interval


Allowed interval:


- day
- hour



Output:


List[TimeSeriesPoint]



# Tenant Isolation Boundary


Authentication:

Deferred.


Authorization boundary:

Mandatory.


Every request:


- MUST require organization scope
- MUST enforce organization isolation
- MUST hide cross-organization access



# Storage Policy


No new tables.

No migration.

No cache.

No materialized views.



# File Boundary


Allowed additions:


costguard_split/api/*

costguard_split/visualization/*

tests/split_p1c02_trend_visualization_test.py



Forbidden:


costguard_split/ingest/*

costguard_split/connectors/*

costguard_split/identity/*

pricing logic



# Required Tests


| ID | Requirement |
|----|-------------|
| V1 | trend returns TimeSeries DTO |
| V2 | daily trend works |
| V3 | hourly trend works |
| V4 | half-open interval preserved |
| V5 | organization isolation |
| V6 | NULL cost preserved |
| V7 | no mutation |
| V8 | no raw content exposure |
| V9 | no private intelligence symbols |



# Authorization Status


Current:


READ GATE ONLY


Coding:


NOT AUTHORIZED


Requires:


- implementation plan
- file boundary approval
- test plan approval

