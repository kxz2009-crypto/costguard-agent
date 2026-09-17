# CostGuard Split P1D-03 Report Generation Gate v0.1


# Classification

P1D-03 = OPEN Report Generation


This gate renders static analytics reports from existing read
models only.


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
- file writes inside the service function
- email / webhook / scheduled delivery


# Baseline


Release baseline:

v0.6.1-p1d02


Commit:

Current P1D-02 completion baseline.


Scope:

Post P1D-02 dashboard read projection.


# Objective

Render deterministic, human-readable static report documents from
existing analytics read models.


The implementation MUST:

- consume existing analytics_summary read model
- consume existing timeseries_summary read model
- consume existing visualization distributions
- remain read only
- preserve analytics boundary
- avoid direct database access
- avoid duplicate aggregation logic
- avoid business decisions
- produce deterministic output (identical inputs -> identical text)


# Architecture Boundary



Allowed:

report service

 |

analytics / timeseries / visualization services

 |

existing DTOs

Forbidden:

report service

 |

usage_events database

Rules:

Report layer MUST NOT:

- execute SQL
- access usage_events directly
- perform GROUP BY aggregation
- calculate cost
- interpret numbers (no "spike", "unusual", "trending" language)
- write files; rendering returns a string, caller owns I/O


# Allowed Capability

OPEN:


- summary report (Markdown text):
  totals table + provider/model distribution tables


- timeseries report (Markdown text):
  per-bucket usage table preserving point order


- report envelope (ReportDocument):
  meta block (schema_version, baseline, window, granularity,
  filters echo) + rendered markdown body


NOT INCLUDED:

- PDF / HTML rendering
- templates engine
- chart images
- delivery / scheduling
- i18n


# Contract


Determinism:

- identical inputs MUST produce byte-identical report text
- no timestamps inside the rendered body
- table rows in source order (no sorting beyond existing layers)


Integrity:

- envelope meta mirrors export/dashboard conventions:
  schema_version, baseline, window, granularity, filters echo
- body carries a content_hash (sha256 over canonical body bytes)


Privacy:

- report MUST NOT include raw request bodies or prompts


Layer form:

- pure functions returning ReportDocument; caller owns I/O


# Acceptance Requirements


Acceptance is whole-suite:

- all prior suites remain green
- new report suite covers:

  - summary report totals row matches analytics totals
  - summary report distribution rows match visualization output
  - timeseries report rows match timeseries output in order
  - determinism: two renders, byte-identical text
  - envelope content_hash matches body
  - meta completeness (schema_version, baseline, window,
    granularity, filters)
  - org isolation: other-org events never appear
  - read-only: no db mutation
  - boundary: module imports no db module, no sqlite3, writes no files
  - interpretation ban: body contains no judgement vocabulary
    ("trend", "spike", "anomal", "recommend")


# File Boundary

Allowed new files:

- costguard_split/report/__init__.py
- costguard_split/report/dto.py
- costguard_split/report/service.py
- tests/split_p1d03_report_test.py

Forbidden:

- modifications to analytics, visualization, export or dashboard
  modules
- new dependencies (stdlib only)
- database schema changes


# Exit Criteria


- gate requirements satisfied
- whole suite green (pytest and unittest)
- implementation committed as feat(split) separate from docs(split)
- release tagged v0.7.0-p1d03 after acceptance
