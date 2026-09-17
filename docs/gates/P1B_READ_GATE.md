# CostGuard Split P1B Read Gate v0.1

## Baseline

HEAD:
v0.3.0-p1a

Scope:
Post P1A capability planning.

## Current Capability Boundary

P1A provides:

- usage event ingestion
- provider connectors
- token accounting
- public API cost estimation
- tenant/device/member attribution

## OPEN Candidates

Allowed:

- usage aggregation
- time-series statistics
- provider/model summaries
- read-only reports
- dashboards based on stored facts

## NOT AUTHORIZED

Forbidden:

- enterprise contract pricing
- billing reconciliation
- quota management
- cost allocation
- optimization engine
- recommendation engine
- learned intelligence

## Proposed Sequence

P1B-01:
Usage Analytics Read Model

P1B-02:
Cost Visualization

P1B-03:
Provider and Model Comparison

P1B-04:
Recommendation Features
(requires separate gate)

