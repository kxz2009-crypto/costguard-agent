# CostGuard Split P1C-02 Trend Visualization Plan v0.1


# Classification

P1C-02 = OPEN Trend Visualization Layer


This implementation exposes existing time-series analytics projections only.


NOT AUTHORIZED:

- billing
- cost calculation
- quota management
- allocation intelligence
- optimization
- recommendation
- forecasting
- anomaly detection



# Baseline


Depends on:

v0.5.0-p1c01


Scope:

Post P1C-01 TimeSeries analytics read model.



# Objective


Expose time-series analytics through visualization API layer.


The implementation MUST:


- consume existing TimeSeries DTO
- use existing timeseries_summary()
- remain read only
- preserve analytics boundary
- avoid duplicate aggregation logic
- avoid direct database access in visualization layer
- avoid business decisions



# Architecture Boundary


Allowed:


HTTP

 |

visualization API adapter

 |

analytics.timeseries_summary()

 |

TimeSeriesPoint DTO



Forbidden:


HTTP

 |

usage_events database



Visualization layer MUST NOT:


- execute SQL
- query usage_events directly
- perform bucket aggregation
- calculate cost
- generate predictions
- add intelligence logic



# Scope


OPEN:


- trend endpoint
- daily trend
- hourly trend
- TimeSeriesPoint serialization
- organization isolation


NOT INCLUDED:


- forecasting
- anomaly detection
- alerts
- billing
- pricing
- optimization



# Endpoint Contract


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


list[TimeSeriesPoint]



Example:


[
 {
   bucket_start,
   bucket_end,
   events,
   request_count,
   tokens,
   public_cost_nullable
 }
]



# Tenant Isolation Boundary


Authentication:


Deferred.


Authorization boundary:


Mandatory.


Every request:


- MUST require organization scope
- MUST enforce organization isolation
- MUST hide cross organization access



# Storage Strategy


No migration.

No new tables.

No cache.

No materialized views.



# File Boundary


Allowed additions:


costguard_split/api/trend_visualization.py

tests/split_p1c02_trend_visualization_test.py



Existing dependency:


costguard_split/analytics/timeseries.py


Must not be modified.



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



# Implementation Authorization


Status:


PLAN ONLY


Coding requires:


- plan approval
- file boundary approval
- test plan approval
