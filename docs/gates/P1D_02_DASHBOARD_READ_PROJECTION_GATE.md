# CostGuard Split P1D-02 Dashboard Read Projection Gate v0.1


# Classification

P1D-02 = OPEN Dashboard Read Projection


This gate assembles existing read models into one dashboard payload only.


NOT AUTHORIZED:

- billing
- pricing logic
- quota management
- allocation intelligence
- optimization
- recommendation
- forecasting
- anomaly detection
- new aggregation logic
- UI rendering / frontend assets


# Baseline


Release baseline:

v0.6.0-p1d01


Commit:

Current P1D-01 completion baseline.


Scope:

Post P1D-01 analytics export layer.


# Objective

Provide one aggregated, dashboard-ready read model assembled from
existing analytics, timeseries and visualization outputs.


The implementation MUST:

- consume existing analytics_summary read model
- consume existing timeseries_summary read model
- consume existing visualization distributions
- remain read only
- preserve analytics boundary
- avoid direct database access
- avoid duplicate aggregation logic
- avoid business decisions


# Architecture Boundary



Allowed:

dashboard projection service

 |

analytics / timeseries / visualization services

 |

existing DTOs

Forbidden:

dashboard projection service

 |

usage_events database

Rules:

Dashboard projection MUST NOT:

- execute SQL
- access usage_events directly
- perform GROUP BY aggregation
- calculate cost
- generate predictions
- cache across requests (stateless per call)


# Allowed Capability

OPEN:


- dashboard_projection(db, org, window, granularity, filters)
  returning one DashboardPayload document


Payload sections (all sourced from existing layers):

- totals (visualization summary)
- provider_distribution / model_distribution
- trend (time series points)
- generated meta: schema_version, baseline, window, granularity,
  filters echo


NOT INCLUDED:

- websocket / live push
- per-user dashboards / tenancy beyond existing org check
- chart configuration
- alerts


# Contract


Determinism:

- identical inputs MUST produce equal payloads (dict equality)


Integrity:

- meta block carries schema_version, baseline, window (start, end),
  granularity, filters echo


Privacy:

- payload MUST NOT include raw request bodies or prompts


Layer form:

- pure service function returning a dict; HTTP exposure is a
  separate concern and NOT part of this slice


# Acceptance Requirements


Acceptance is whole-suite:

- all prior suites remain green
- new dashboard suite covers:

  - payload sections match analytics / visualization / timeseries
    outputs directly
  - determinism: two calls, same inputs, equal payloads
  - meta completeness (schema_version, baseline, window,
    granularity, filters)
  - org isolation: other-org events never appear
  - read-only: no db mutation
  - boundary: module imports no db module, no sqlite3
  - granularity validation delegated (unsupported granularity
    surfaces the existing timeseries error, not a new one)


# File Boundary

Allowed new files:

- costguard_split/dashboard/__init__.py
- costguard_split/dashboard/dto.py
- costguard_split/dashboard/service.py
- tests/split_p1d02_dashboard_test.py

Forbidden:

- modifications to analytics, visualization or export modules
- new dependencies (stdlib only)
- database schema changes
- HTTP routes in this slice


# Exit Criteria


- gate requirements satisfied
- whole suite green (pytest and unittest)
- implementation committed as feat(split) separate from docs(split)
- release tagged v0.6.1-p1d02 after acceptance
