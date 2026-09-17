# Hermes AutoDev State Management v0.1


## 1. Purpose

Define persistent task state management for Hermes DevOS.

The purpose is to prevent:

- duplicate execution
- lost progress
- repeated failures
- context reset


---

# 2. Task State Machine

CREATED

|

v

PLANNED

|

v

RUNNING

|

v

TESTING

|

v

REVIEWING

|

v

DONE



Failure flow:



RUNNING

|

v

FAILED

|

v

RETRY

|

v

ESCALATED



---

# 3. State Storage


Each task stores:


```yaml
task_id:

status:

created_at:

updated_at:

worker:

changes:

tests:

review:

next_action:
4. Recovery Rules

If interrupted:

Resume from last stable state.

Examples:

RUNNING

↓

resume execution

TESTING

↓

continue validation

REVIEWING

↓

continue review

5. Principles

State first.

Execution second.

Never lose progress.
