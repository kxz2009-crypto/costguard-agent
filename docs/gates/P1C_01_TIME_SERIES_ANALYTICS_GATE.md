# CostGuard Split P1C-01 Time Series Analytics Read Model Gate v0.1


# Classification

P1C-01 = OPEN Time Series Analytics Read Model


This gate authorizes creation of a read-only time dimension aggregation layer.

This gate does NOT authorize:

- dashboard logic
- public API exposure
- billing
- pricing engine
- quota management
- allocation intelligence
- optimization
- recommendation
- commercial intelligence



# Baseline

Release baseline:

v0.4.2-p1b03-final


Commit:

6316b89


Scope:

Post P1B visualization API layer.



# Objective


Create a dedicated time-series analytics read model.

Purpose:

Transform existing analytics facts into time-based aggregation DTOs.


The time-series layer MUST:

- be read only
- preserve usage_events as source data
- not mutate ingestion data
- not calculate alternative pricing
- not introduce business decisions



# Architecture Boundary


Allowed:


usage_events

    |

    v

analytics time-series service

    |

    v

Trend DTO



Visualization API may consume this layer in a future gate.



Forbidden:


usage_events

    |

    v

HTTP API direct query



# Allowed Capability


OPEN:

- daily aggregation
- hourly aggregation
- token trend
- event trend
- public stored cost trend
- time window filtering



# Time Semantics


All aggregation MUST use:

[start, end)


Half-open interval.


Example:

started_at >= start

AND

started_at < end



# Money Policy


api_equivalent_cost_usd:


Allowed:

- aggregate existing stored public estimates


Forbidden:

- repricing
- filling NULL values
- alternative pricing calculation
- inferred cost



# Storage Strategy


Default:


NO migration.

NO new tables.

NO materialized views.

NO cache.



The initial implementation MUST calculate from existing read source.



# File Boundary


Allowed additions:


costguard_split/analytics/timeseries.py

costguard_split/analytics/timeseries_dto.py

tests/split_p1c01_timeseries_test.py



Forbidden modifications:


costguard_split/ingest/*

costguard_split/connectors/*

costguard_split/identity/*

costguard_split/api/*

pricing logic



# Required Tests


| ID | Requirement |
|----|-------------|
| T1 | daily aggregation correctness |
| T2 | hourly aggregation correctness |
| T3 | half-open time boundary |
| T4 | organization isolation |
| T5 | NULL cost preservation |
| T6 | no mutation |
| T7 | no raw content exposure |
| T8 | no private intelligence symbols |



# Authorization Status


Current:

READ GATE ONLY


Coding:

NOT AUTHORIZED


Requires:

- implementation plan
- file boundary approval
- test plan approval
