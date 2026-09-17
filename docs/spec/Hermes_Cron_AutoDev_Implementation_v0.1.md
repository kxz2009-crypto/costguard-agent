# Hermes Cron AutoDev Implementation v0.1


## 1. Purpose

Define the implementation architecture for Hermes Night AutoDev scheduling.

This document converts:

Hermes Night AutoDev Workflow

into executable automation.


---

# 2. Architecture

Hermes Cron

  |

  v

DevOS Scheduler

  |

  v

Task Collector

  |

  v

Task Queue

  |

  +-------------+

  |             |

coder       reviewer

  |

  v

Report Generator



---

# 3. Scheduler


## Schedule Window


Timezone:


Asia/Shanghai



Active period:


23:10 - 09:00



Main trigger:



23:10


Start nightly workflow.


---

# 4. Cron Responsibilities


Cron only starts workflow.

Cron does NOT:

- write code
- decide tasks
- modify repository


Cron launches:



night-autodev entrypoint



---

# 5. Entry Point


Recommended:



~/.hermes/scripts/night-autodev.sh



Responsibilities:


1. initialize environment

2. activate DevOS profile

3. create execution session

4. start task discovery


---

# 6. Task Discovery


Component:



collect_tasks.py



Sources:


## Repository


Collect:



git status

recent commits

TODO

FIXME

failed tests



## Project documents


Read:



docs/spec

docs/plans

roadmap



## Previous reports


Read:



execution history

failed tasks

pending tasks



---

# 7. Task Queue


Generated format:


```yaml
tasks:

  - id:
    objective:
    priority:
    risk:
    worker:
    validation:

Example:

tasks:

  - id: CG-001

    objective:
      add unit tests

    priority:
      medium

    risk:
      low

    worker:
      coder

    validation:
      reviewer
8. Worker Execution
coder

Input:

task object

Actions:

inspect code
implement change
run tests
generate report

Output:

completion report
reviewer

Triggered:

For:

medium risk
high risk
release candidates

Actions:

inspect diff
verify tests
evaluate risks

Output:

approve

or

request changes
9. Failure Handling
coder failure

Retry:

maximum 2 times

If still failed:

Escalate:

devos

↓

Codex
10. Safety Gate

Automatic workflow MUST stop when:

unclear requirement
production impact
security risk
destructive operation
payment related change

Require:

human approval

11. Logging

Every execution creates:

~/.hermes/logs/night-autodev/

Structure:

YYYY-MM-DD/

    session.log

    tasks.yaml

    coder/

    reviewer/

    report.md
12. Morning Report

Generated before:

09:00

Contains:

Summary
completed tasks
failed tasks
changed files
Quality
tests
review result
Next Actions
pending tasks
human decisions
13. Future Extension

Possible integration:

VPS Hermes workers
GitHub Actions
CI/CD
automatic issue creation
multi-agent parallel execution
Principle

Cron starts.

DevOS decides.

Coder executes.

Reviewer validates.

Codex rescues.

Human controls.
