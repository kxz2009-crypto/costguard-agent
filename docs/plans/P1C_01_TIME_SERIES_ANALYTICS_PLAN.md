# CostGuard Split P1C-01 Time Series Analytics Read Model Plan v0.1


# Objective

Implement a read-only time-series analytics aggregation layer.

Purpose:

Provide reusable time bucket aggregation for future visualization trend capabilities.

This plan only creates internal analytics capability.

No HTTP exposure.


# Baseline

Depends on:

v0.4.2-p1b03-final

Current HEAD:

P1C-01 gate approved.


# Architecture


usage_events

    |

    v

analytics.timeseries

    |

    v

TimeSeries DTO



# Scope


OPEN:

- hourly aggregation
- daily aggregation
- token aggregation
- event aggregation
- stored public cost aggregation


NOT INCLUDED:

- API endpoint
- dashboard
- billing
- pricing
- optimization
- recommendation
- forecasting



# Data Source


Single source:

usage_events


No new storage.

No migration.

No cache.

No materialized view.



# Time Bucket Rules


Supported granularities:


hour

day


Bucket semantics:

[start, end)


Example:

hour bucket:

2026-01-01 10:00 <= started_at < 2026-01-01 11:00



# Cost Rules


Allowed:

Aggregate existing:

api_equivalent_cost_usd


Rules:

- NULL remains NULL
- no recalculation
- no price lookup
- no estimate generation



# File Boundary


Create:


costguard_split/analytics/timeseries.py

costguard_split/analytics/timeseries_dto.py

tests/split_p1c01_timeseries_test.py



Do not modify:


costguard_split/api/*

costguard_split/ingest/*

costguard_split/connectors/*

costguard_split/identity/*



# DTO Design


TimeSeriesPoint:


- bucket_start
- bucket_end
- events
- request_count
- input_tokens
- cached_input_tokens
- cache_write_tokens
- output_tokens
- reasoning_tokens
- public_cost_nullable



# Service Contract


Function:


timeseries_summary(
    db,
    organization_id,
    start,
    end,
    granularity
)


Returns:

list[TimeSeriesPoint]


# Testing Requirements


| ID | Requirement |
|----|-------------|
| T1 | daily aggregation |
| T2 | hourly aggregation |
| T3 | half-open interval |
| T4 | organization isolation |
| T5 | NULL cost preservation |
| T6 | read-only behavior |
| T7 | no raw content |
| T8 | no intelligence layer |



# Implementation Authorization


Status:

PLAN ONLY


Coding requires plan approval.
