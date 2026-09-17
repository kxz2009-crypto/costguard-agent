# Hermes DevOS Agent Implementation Guide v0.1


## 1. Purpose

Define agent responsibilities during DevOS implementation.


---

# 2. Agent Roles


## devos profile


Responsibility:

- architecture decisions
- task routing
- workflow control


---

## coder profile


Responsibility:

- implement runtime scripts
- write tests
- maintain code quality


Tasks:


- night-autodev.sh
- collect_tasks.py
- task_state.py
- report.py


---

## reviewer profile


Responsibility:

- review implementation
- check safety
- verify design compliance


---

## Codex


Responsibility:

Emergency engineering support.


Use for:


- difficult debugging
- architecture conflict
- complex refactoring


---

## qwenmedical


Responsibility:


Medical knowledge workflows only.


---

# 3. Implementation Rules


Agents must:


- read docs/spec first
- minimize changes
- verify output
- keep logs


Agents must not:


- modify production data
- bypass approval
- change architecture without review


---

# 4. Delivery Standard


Every implementation must provide:


- changed files
- test result
- known risks
- next action
