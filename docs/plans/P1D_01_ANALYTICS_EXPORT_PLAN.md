# CostGuard Split P1D-01 Analytics Export Plan v0.1


# Classification

P1D-01 = OPEN Analytics Export Layer


This implementation serializes existing analytics projections only.


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

v0.5.1-p1c02


Scope:

Post P1C-02 trend visualization layer.


# Objective

Provide deterministic JSON export documents for analytics read models.

The implementation MUST:

- consume existing AnalyticsSummary DTO (analytics_summary)
- consume existing TimeSeries DTO (timeseries_summary)
- consume existing visualization distributions (visualization_summary)
- remain read only
- preserve analytics boundary
- avoid duplicate aggregation logic
- avoid direct database access in export layer
- avoid business decisions


# Architecture Boundary


Allowed call chain:

export service function

 |

existing analytics / visualization services

 |

existing DTOs

Forbidden:

export service function

 |

usage_events table

Rules:

- export module MUST NOT import costguard_split.db
- export module MUST NOT import sqlite3
- export module MUST NOT open files; caller receives a dict


# Design


## Module Layout

costguard_split/export/

- __init__.py (public re-exports)
- dto.py (ExportManifest, ExportDocument dataclasses)
- service.py (summary_export, timeseries_export, distribution_export)


## Export Document Shape

{
  "manifest": {
    "schema_version": "1",
    "generated_from": "analytics" | "timeseries" | "distribution",
    "baseline": <baseline tag string>,
    "window": {"start": ..., "end": ...},
    "filters": {"provider": ..., "model": ..., "member_id": ..., "device_id": ...},
    "content_hash": <sha256 of payload block>
  },
  "payload": { ... existing DTO serialization ... }
}


## Determinism Contract

- json.dumps(payload, sort_keys=True, separators=(",", ":")) for hashing
- manifest.content_hash = sha256 over canonical payload bytes
- two identical calls return byte-identical documents when re-serialized
  with the same dump call


## Data Flow

summary_export(db, org, start, end, **filters)
  -> analytics_summary(db, org, start, end, **filters)  (existing)
  -> asdict() -> payload

timeseries_export(db, org, start, end, granularity, **filters)
  -> timeseries_summary(...)  (existing)
  -> point list preserved in original order

distribution_export(db, org, start, end, **filters)
  -> visualization_summary(...)  (existing)
  -> provider/model distributions preserved


# Test Plan

tests/split_p1d01_export_test.py

- test_summary_export_echoes_analytics_fields
- test_timeseries_export_preserves_point_order
- test_distribution_export_matches_visualization_output
- test_export_determinism_bytes_identical
- test_manifest_content_hash_matches_payload
- test_manifest_filters_echo_inputs
- test_export_does_not_mutate_db (row counts before/after)
- test_export_module_does_not_import_db (source inspection or sys.modules probe)

Fixture strategy: reuse existing P1A ingest fixtures pattern
(temp schema, seeded usage_events, in-memory sqlite via existing helpers).


# Exit Criteria

- whole suite green (unittest and pytest compatible)
- gate P1D_01 requirements satisfied
- implementation commit: feat(split): add P1D-01 analytics export layer
- docs commit precedes implementation commit
- release tag v0.6.0-p1d01 after acceptance
