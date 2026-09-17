# CostGuard Split P1D-01 Analytics Export Gate v0.1


# Classification

P1D-01 = OPEN Analytics Export Layer


This gate exposes existing analytics projections as static export artifacts only.


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


# Baseline


Release baseline:

v0.5.1-p1c02


Commit:

Current P1C-02 completion baseline.


Scope:

Post P1C-02 trend visualization layer.


# Objective

Serialize existing analytics read models into portable export documents.


The implementation MUST:


- consume existing AnalyticsSummary DTO
- consume existing TimeSeries DTO
- consume existing visualization distributions
- remain read only
- preserve analytics boundary
- avoid direct database access
- avoid duplicate aggregation logic
- avoid business decisions


# Architecture Boundary



Allowed:

export service

 |

analytics service

 |

analytics DTO

Forbidden:

export service

 |

usage_events database

Rules:

Export layer MUST NOT:

- execute SQL
- access usage_events directly
- perform GROUP BY aggregation
- calculate cost
- generate predictions
- mutate analytics state


# Allowed Capability

OPEN:


- summary export document (JSON)
- time series export document (JSON)
- distribution export document (JSON)


NOT INCLUDED:

- CSV / XLSX formats
- scheduled delivery
- email / webhook transport
- report templates
- dashboards


# Export Contract


Determinism:

- identical inputs MUST produce byte-identical export payloads
- keys sorted, stable field order


Integrity:

- each export document carries a manifest block
- manifest records: generated_from (layer name), baseline tag,
  window (start, end), filters echo (provider, model, member_id,
  device_id), schema_version


Privacy:

- export MUST NOT include raw request bodies or prompts
- export MUST NOT include organization-external identifiers


Format:

- UTF-8 JSON, one document per export call
- no filesystem writes inside the service function; caller owns I/O


# Acceptance Requirements


Acceptance is whole-suite:

- all prior suites remain green
- new export suite covers:

  - summary export round trip (fields echo analytics_summary DTO)
  - timeseries export preserves point order and bucket boundaries
  - distribution export matches visualization_summary output
  - determinism: two calls, same inputs, byte-identical bytes
  - manifest completeness
  - read-only: export never writes (no db mutation assertions)
  - boundary: export service module imports no db module


# File Boundary

Allowed new files:

- costguard_split/export/__init__.py
- costguard_split/export/dto.py
- costguard_split/export/service.py
- tests/split_p1d01_export_test.py

Forbidden:

- modifications to analytics or visualization modules
- new dependencies (stdlib only)
- database schema changes


# Exit Criteria


- gate requirements satisfied
- whole suite green
- implementation committed as feat(split) separate from docs(split)
- release tagged v0.6.0-p1d01 after acceptance
