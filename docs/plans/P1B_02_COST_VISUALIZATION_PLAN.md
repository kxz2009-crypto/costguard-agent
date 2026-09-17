# CostGuard Split P1B-02 Cost Visualization Implementation Plan v0.1


# Classification

P1B-02 = OPEN Visualization Layer

This implementation exposes existing analytics facts for visualization.

No commercial intelligence is introduced.


---

# Baseline

Gate:

P1B_02_COST_VISUALIZATION_GATE.md


Release:

v0.4.0-p1b01


Commit:

2d4887ee7d1849fbbfdadbedf90223c6765981d3


---

# Objective

Implement read-only visualization DTO generation
on top of analytics read service.


Goals:

- trend chart data
- distribution chart data
- summary cards
- public cost display


Non-goals:

- pricing engine
- billing
- optimization
- recommendation
- forecasting
- decision support


---

# Architecture


analytics service

        |

        v

visualization service

        |

        v

visualization DTO


Visualization layer MUST NOT:

- query database directly
- access usage_events directly
- modify analytics DTO
- mutate storage


---

# Proposed Files


Allowed:


costguard_split/visualization/__init__.py

costguard_split/visualization/dto.py

costguard_split/visualization/service.py


Tests:


tests/split_p1b_visualization_test.py



---

# DTO Design


## UsageTrendPoint


Fields:


date

events

tokens

public_cost_nullable



## DistributionPoint


Fields:


key

events

tokens



## VisualizationSummary


Fields:


events

tokens

public_cost_nullable



---

# Functions


## usage_trend()


Input:

organization_id

start

end


Output:

list[UsageTrendPoint]



## provider_distribution()


Input:

organization_id

start

end


Output:

list[DistributionPoint]



## model_distribution()


Input:

organization_id

start

end


Output:

list[DistributionPoint]



## visualization_summary()


Input:

organization_id

start

end


Output:

VisualizationSummary



---

# Money Handling


Allowed:


Read existing public cost.


Forbidden:


- calculate new price
- apply pricing table
- fill missing cost
- infer hidden cost


NULL remains NULL.


---

# Test Plan


V1 trend aggregation

V2 provider distribution

V3 model distribution

V4 summary aggregation

V5 cost passthrough

V6 NULL cost behavior

V7 organization isolation

V8 no mutation

V9 no raw content

V10 no private symbols


---

# Review Status


Implementation:

NOT STARTED


Requires:

- plan approval
- code review
- acceptance tests

