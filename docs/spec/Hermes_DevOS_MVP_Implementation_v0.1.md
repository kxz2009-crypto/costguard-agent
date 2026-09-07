# Hermes DevOS MVP Implementation v0.1


## 1. Objective


Implement the first runnable version of Hermes DevOS.


MVP goal:

Provide autonomous project observation and task management.


Not included:

- automatic code modification
- automatic deployment
- destructive operation


---

# 2. MVP Architecture


Hermes Cron

  |

  v

night-autodev.sh

  |

  v

Task Collector

  |

  v

Task State Manager

  |

  v

Report Generator



---

# 3. Components


## 3.1 Scheduler


Entry:


night-autodev.sh



Responsibilities:

- load environment
- activate devos profile
- create session
- start workflow


---

## 3.2 Task Collector


File:


collect_tasks.py



Input:


Repository:


git status

git log

TODO

FIXME

docs/plans

test results



Output:



tasks.yaml



---

## 3.3 State Manager


File:


task_state.py



Maintain:



CREATED

PLANNED

OBSERVED

REPORTED



Storage:



~/.hermes/state/autodev/



---

## 3.4 Report Generator


File:


report.py



Output:



Night_AutoDev_Report.md



Contains:

- repository status
- detected tasks
- risk level
- recommendation


---

# 4. Execution Rules


MVP only observes.


Allowed:

- read repository
- analyze status
- generate reports


Forbidden:

- modify source code
- commit changes
- push changes


---

# 5. Future Expansion


v0.2:

Enable coder execution


v0.3:

Enable reviewer gate


v0.4:

Enable VPS worker


v1.0:

Full autonomous development loop


---

# Principle


Observe first.

Automate second.

Execute last.
