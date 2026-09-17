# Hermes Night Runtime Specification v0.1


# Objective


Define automatic night development runtime for Local Hermes.


Execution window:


Timezone:

Asia/Shanghai


Start:

23:10


End:

09:00



# Runtime Role


Local Hermes is the controller.


Responsibilities:


- task scheduling
- model routing
- permission control
- result aggregation



# Night Pipeline



## Phase 1 - Initialization


At 23:10:


Execute:


1. load project status

2. check git branch

3. read roadmap

4. read pending tasks



Required information:


- current commit
- uncommitted files
- open issues
- unfinished tasks



# Phase 2 - Task Planning


Hermes creates execution queue.


Each task requires:


task_id

goal

scope

profile

model

acceptance criteria



Example:


task_id:

P1C-03


profile:

dev


executor:

Codex



# Phase 3 - Execution Routing



## Documentation Tasks


Route:


Research Profile


Models:


GLM-5.3-Flash

GLM-5.3

K3



## Coding Tasks


Route:


Dev Profile


Executor:


Codex



## Review Tasks


Route:


Review Profile


Models:


GLM-5.3

GPT-5.6



# Phase 4 - Validation


Every code task requires:


1.

syntax check


2.

unit test


3.

git diff review


4.

security boundary check



Failure:


stop commit.


Create troubleshooting task.



# Phase 5 - Commit Policy


Automatic commit allowed:


Only when:


- tests pass
- scope unchanged
- no forbidden file modified



Commit message format:


type(scope): description



Examples:


feat(split): add P1C-03 module


test(split): add acceptance tests



# Codex Rules


Codex is an execution engine.


Codex should NOT:


- decide architecture
- modify specifications
- expand scope


Codex receives:


approved plan

file boundary

acceptance tests



# Model Escalation


Default:


GLM-5.3-Flash


If complex reasoning:


GLM-5.3


If long context:


Kimi K3


If critical:


GPT-5.6


Fallback:


DeepSeek



# VPS Hermes Role


VPS Hermes performs:


- remote verification
- regression testing
- environment validation



VPS Hermes does NOT:


- modify architecture
- directly commit code



# Daily Report


At completion generate:


## Summary


Completed tasks.


## Commits


Git commits.


## Tests


Passed tests.


## Problems


Failures.


## Next Queue


Remaining tasks.



# Safety Rules


Never automatically:


- delete files
- change credentials
- deploy production
- modify security policy



# Principle


Night runtime is autonomous execution.

Local Hermes controls.

Codex changes.

Models reason.

VPS validates.


