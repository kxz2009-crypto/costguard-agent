# CostGuard Split P1D-02 Dashboard Read Projection Plan v0.1


# Classification

P1D-02 = OPEN Dashboard Read Projection


This implementation assembles existing read models only.


NOT AUTHORIZED:

- billing
- cost calculation
- quota management
- allocation intelligence
- optimization
- recommendation
- forecasting
- anomaly detection
- HTTP routes (separate concern, not this slice)


# Baseline

Depends on:

v0.6.0-p1d01


Scope:

Post P1D-01 analytics export layer.


# Objective

One dashboard-ready payload assembled from existing layers.

The implementation MUST:

- consume existing analytics_summary
- consume existing timeseries_summary
- consume existing visualization distributions
- remain read only and stateless per call
- preserve analytics boundary
- avoid duplicate aggregation logic
- avoid direct database access
- avoid business decisions


# Architecture Boundary


Allowed call chain:

dashboard service function

 |

analytics_summary / timeseries_summary /
visualization_summary + distributions

 |

existing DTOs

Forbidden:

dashboard service function

 |

usage_events table

Rules:

- dashboard module MUST NOT import costguard_split.db
- dashboard module MUST NOT import sqlite3
- dashboard module MUST NOT open files
- dashboard module MUST NOT register HTTP routes


# Design


## Module Layout

costguard_split/dashboard/

- __init__.py (public re-exports)
- dto.py (DashboardMeta, DashboardPayload dataclasses)
- service.py (dashboard_projection)


## Payload Shape

DashboardPayload.to_dict() ->

{
  "meta": {
    "schema_version": "1",
    "baseline": <baseline tag>,
    "window": {"start": ..., "end": ...},
    "granularity": <"day"|"hour">,
    "filters": {"provider": ..., "model": ...,
                "member_id": ..., "device_id": ...}
  },
  "totals": {events, tokens, public_cost_nullable},
  "provider_distribution": [ {dimension, key, events, tokens} ],
  "model_distribution":    [ {dimension, key, events, tokens} ],
  "trend": [ {bucket_start, bucket_end, events, ...} ]
}


## Data Flow

dashboard_projection(db, organization_id, start, end,
                     granularity, **filters)

  summary = analytics_summary(...)            (existing)
  totals = visualization_summary(summary)     (existing)
  providers = provider_distribution(summary)  (existing)
  models = model_distribution(summary)        (existing)
  trend = timeseries_summary(...)             (existing)

Unsupported granularity is NOT pre-validated here; the existing
timeseries layer raises ValueError and that error surfaces as-is
(delegation of validation, no duplicate rules).


# Test Plan

tests/split_p1d02_dashboard_test.py

- test_payload_totals_match_visualization_summary
- test_payload_distributions_match_visualization_output
- test_payload_trend_matches_timeseries_output
- test_payload_determinism_equal_payloads
- test_meta_completeness (schema_version, baseline, window,
  granularity, filters echo)
- test_org_isolation (other-org events absent)
- test_projection_does_not_mutate_db
- test_module_does_not_import_db_or_sqlite3
- test_unsupported_granularity_surfaces_timeseries_error

Fixture strategy: mirror P1D-01 suite fixture (full usage_events
schema, org-a / org-b seeds).


# Exit Criteria

- whole suite green (pytest and unittest compatible)
- gate P1D_02 requirements satisfied
- implementation commit: feat(split): add P1D-02 dashboard read
  projection
- docs commit precedes implementation commit
- release tag v0.6.1-p1d02 after acceptance
