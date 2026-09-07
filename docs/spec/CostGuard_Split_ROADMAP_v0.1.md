# CostGuard Split Roadmap v0.1


# Development Philosophy


CostGuard follows a gated engineering workflow.


Development lifecycle:


Gate

↓

Plan

↓

Implementation

↓

Acceptance Test

↓

Boundary Review

↓

Release Tag



No implementation without approved scope.



---


# Completed Releases


## P0 Foundation


Status:

COMPLETED


Includes:


- repository split foundation
- identity boundary
- device registration
- member management
- assignment model
- ingestion foundation



---


# P1A Usage Ingestion


Status:

COMPLETED


Capability:


- usage event ingestion
- immutable event storage
- connector boundary



---


# P1B Analytics Foundation


Status:

COMPLETED


Release:


v0.4.x



Includes:


- usage analytics read model
- visualization DTO layer
- internal visualization API adapter



Architecture:


usage_events

↓

analytics read model

↓

visualization projection



---


# P1C Analytics Projection


Status:

COMPLETED


Release:


v0.5.x



Includes:


## P1C-01

Time Series Analytics Read Model


Capability:


- hourly aggregation
- daily aggregation
- token aggregation
- stored public cost aggregation



## P1C-02

Trend Visualization Layer


Capability:


- hourly trend
- daily trend
- visualization projection



---


# Next Phase


# P1D Product Consumption Layer


Objective:


Expose existing analytics capability for human consumption.



Allowed:


- dashboard projection
- export
- reporting
- internal consumption API



Not Included:


- billing
- pricing engine
- quota system
- optimization
- recommendation
- intelligence



Planned slices:


## P1D-01 Analytics Export Layer


Purpose:


Export existing analytics projections.


No new calculation.


---


## P1D-02 Dashboard Read Projection


Purpose:


Provide dashboard-ready read models.


No business logic.


---


## P1D-03 Report Generation


Purpose:


Generate static analytics reports.


No recommendation.


---


## P1D-04 Open Consumption API


Purpose:


Stable external consumption interface.


Requires separate API gate.



---


# Future Commercial Layer


# P2 Commercial Capability


Future scope:


- billing
- subscription
- tenant management
- payment



Requires independent authorization.



---


# Future Intelligence Layer


# P3 Intelligence Capability


Future scope:


- AI explanation
- assistant
- insight generation
- automated analysis



Requires private intelligence gate.



---


# Enterprise Layer


# P4 Enterprise Capability


Future scope:


- RBAC
- audit
- compliance
- enterprise deployment
- multi-region



---


# Architecture Principle


CostGuard grows by adding controlled capability layers.


Core data path:


usage_events

↓

analytics

↓

timeseries

↓

visualization

↓

product consumption

↓

commercial capability

↓

intelligence capability



Each layer requires independent authorization.

