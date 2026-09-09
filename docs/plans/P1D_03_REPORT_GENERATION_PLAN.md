# CostGuard Split P1D-03 Report Generation Plan v0.1


# Classification

P1D-03 = OPEN Report Generation


This implementation renders existing read models into static
Markdown reports only.


NOT AUTHORIZED:

- billing
- cost calculation
- recommendation / interpretation
- HTTP routes
- file writes
- delivery / scheduling


# Baseline

Depends on:

v0.6.1-p1d02


Scope:

Post P1D-02 dashboard read projection.


# Objective

Deterministic static analytics reports.

The implementation MUST:

- consume existing analytics_summary
- consume existing timeseries_summary
- consume existing visualization distributions
- remain read only and stateless per call
- preserve analytics boundary
- avoid duplicate aggregation logic
- avoid direct database access
- produce deterministic, byte-identical output for identical inputs


# Architecture Boundary


Allowed call chain:

report service functions

 |

analytics_summary / timeseries_summary /
visualization_summary + distributions

 |

existing DTOs

Forbidden:

report service functions

 |

usage_events table

Rules:

- report module MUST NOT import costguard_split.db
- report module MUST NOT import sqlite3
- report module MUST NOT open / write files
- report module MUST NOT register HTTP routes
- report body MUST NOT contain interpretation vocabulary
  ("trend", "spike", "anomal", "recommend")


# Design


## Module Layout

costguard_split/report/

- __init__.py (public re-exports)
- dto.py (ReportMeta, ReportDocument dataclasses)
- service.py (summary_report, timeseries_report)


## Report Envelope

ReportDocument.to_dict() ->

{
  "meta": {
    "schema_version": "1",
    "baseline": <baseline tag>,
    "window": {"start": ..., "end": ...},
    "granularity": <"day"|"hour"| None>,
    "filters": {"provider": ..., "model": ...,
                "member_id": ..., "device_id": ...}
  },
  "content_hash": <sha256 over canonical body bytes>,
  "body": <markdown string>
}


## Rendering Rules

Markdown tables, fixed column order, rows in source order:

Summary report body:

# Usage Report

## Totals

| events | request_count | input_tokens | ... |
|---|---|---|---|
| <asdict row> |

## Providers

| key | events | tokens |
(mirrors provider_distribution)

## Models

(mirrors model_distribution)

Timeseries report body:

# Usage Timeseries Report

| bucket_start | bucket_end | events | request_count | ... |
(one row per point, source order)

None renders as empty cell. Numbers render via str().
No generated-at timestamp anywhere in the body.


# Test Plan

tests/split_p1d03_report_test.py

- test_summary_report_totals_match_analytics
- test_summary_report_distributions_match_visualization
- test_timeseries_report_rows_match_timeseries_order
- test_report_determinism_bytes_identical
- test_envelope_content_hash_matches_body
- test_meta_completeness
- test_org_isolation
- test_report_does_not_mutate_db
- test_module_boundaries (no db / sqlite3 / file writes)
- test_no_interpretation_vocabulary


# Exit Criteria

- whole suite green (pytest and unittest compatible)
- gate P1D_03 requirements satisfied
- implementation commit: feat(split): add P1D-03 report generation
- docs commit precedes implementation commit
- release tag v0.7.0-p1d03 after acceptance
