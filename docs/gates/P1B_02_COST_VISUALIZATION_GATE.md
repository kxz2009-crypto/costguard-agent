# CostGuard Split P1B-02 Cost Visualization Gate v0.1


# Classification

P1B-02 = OPEN Visualization Layer

This gate authorizes presentation of existing analytics facts only.

This gate does NOT authorize PRIVATE commercial intelligence.


NOT AUTHORIZED:

- enterprise contract pricing
- billing reconciliation
- quota management
- allocation intelligence
- optimization engine
- recommendation engine
- learned intelligence



# Baseline

Release baseline:

v0.4.0-p1b01

Commit:

2d4887ee7d1849fbbfdadbedf90223c6765981d3

Tag:

v0.4.0-p1b01


Scope:

Post P1B-01 analytics read model.



# Objective

Provide read-only visualization data derived from analytics layer.


Source of truth:

analytics read model


Read path:

usage_events
    |
    v
analytics service
    |
    v
visualization DTO



Visualization MUST:

- be read only
- not mutate usage_events
- not recalculate pricing
- not introduce decision logic



# Allowed Capability


OPEN:

- daily usage trend
- token consumption chart
- provider distribution
- model distribution
- public cost trend
- usage summary cards
- report DTO generation




# Query Contract


Initial implementation provides internal visualization DTO only.


Example:


usage_trend(
    org_id,
    start,
    end,
    interval="day"
)


Return:

{
    series: [
        {
            date,
            events,
            tokens,
            public_cost_nullable
        }
    ]
}


provider_distribution(
    org_id,
    start,
    end
)


Return:

[
    {
        provider,
        tokens,
        events
    }
]


model_distribution(
    org_id,
    start,
    end
)


Return:

[
    {
        model,
        tokens,
        events
    }
]


visualization_summary(
    org_id,
    start,
    end
)


Return:

{
    total_events,
    total_tokens,
    public_cost_nullable
}


cost_trend(
    org_id,
    start,
    end,
    interval="day"
)


Return:

[
    {
        date,
        public_cost_nullable
    }
]


# Money Policy


api_equivalent_cost_usd:


Allowed:

- display existing stored public estimates


Forbidden:

- repricing
- filling NULL values
- alternative pricing calculation
- private cost inference



# API Boundary


Initial implementation:

internal service DTO only.


No public HTTP route.


HTTP exposure requires separate gate.



# Storage Strategy


Default:

NO migration.

NO new tables.

NO materialized views.

NO cache.


Read only from existing analytics service / DTO layer.

No direct usage_events query in visualization implementation.



# File Boundary


Allowed additions:


costguard_split/visualization/*

tests/split_p1b_visualization_test.py


Allowed read dependencies:


costguard_split/analytics/*


Restriction:

- read-only import
- no DTO modification
- no analytics query expansion



Forbidden modifications:


costguard_split/ingest/service.py

costguard_split/connectors/*

costguard_split/identity/*

costguard_split/services/device_registry.py

costguard_split/analytics/*

pricing apply logic

usage_events write path



# Required Test Matrix


| ID | Requirement |
|----|-------------|
| V1 | trend aggregation correctness |
| V2 | provider/model distribution |
| V3 | public cost display only |
| V4 | NULL cost handling |
| V5 | organization isolation |
| V6 | no mutation |
| V7 | no raw content exposure |
| V8 | no PRIVATE intelligence symbols |
| V9 | visualization DTO schema stability |



# Authorization Status


Current:

READ GATE ONLY


Coding:

NOT AUTHORIZED


Requires:

- gate review
- implementation plan
- file boundary approval
- test plan approval



# Future Gates


Separate review required for:

- recommendation
- optimization
- commercial intelligence
