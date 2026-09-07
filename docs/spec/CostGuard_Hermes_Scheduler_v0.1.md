# CostGuard Hermes Scheduler v0.1


# 1. Purpose


This document defines the local Hermes scheduling policy.


Goals:

- reduce model cost
- maximize unattended processing
- preserve human approval boundary



# 2. Time Zone


Timezone:

Asia/Shanghai


All schedules MUST use Beijing time.



# 3. Execution Windows


## Interactive Window


Time:

09:00 - 23:10


Purpose:

Human-driven work.


Priority:

Quality > cost


Allowed:

- architecture discussion
- coding decisions
- review
- deployment decision



## Batch Window


Time:

23:10 - 09:00


Purpose:

AI autonomous processing.


Priority:

Cost efficiency > latency



Allowed:


- documentation generation
- test generation
- repository analysis
- code review
- literature processing
- indexing
- summarization



Forbidden:


- production deployment
- release tag creation
- destructive operation
- database migration
- architecture change without approval



# 4. Task Queue


All autonomous tasks MUST enter queue first.


Lifecycle:


pending

↓

running

↓

review

↓

completed



No direct execution without queue record.



# 5. Human Approval Boundary


Human approval required:


- architecture change
- data model change
- security boundary change
- release
- merge to main



AI MAY:


- prepare code
- generate tests
- generate documents
- perform static analysis



# 6. Daily Cycle


23:10

Start batch scheduler.


23:15

Read project state.


00:00

Execute queued tasks.


07:00

Run validation.


08:30

Generate report.


09:00

Stop autonomous execution.



# 7. Failure Policy


If task fails:


DO NOT retry indefinitely.


Create:


failure report

+

diagnostic information
