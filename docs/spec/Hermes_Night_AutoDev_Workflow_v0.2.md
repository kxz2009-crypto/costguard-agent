# Hermes Night AutoDev Workflow v0.2


## 1. Purpose

Hermes Night AutoDev is an autonomous development workflow running during the low-cost inference window.

Operating window:

Beijing Time

23:10 - 09:00


Primary objectives:

- reduce model inference cost
- execute background development tasks
- maintain repository health
- improve software quality
- generate morning reports


---

# 2. System Architecture


             Local Hermes DevOS

                   |
                   |
             Task Scheduler

                   |
    --------------------------------

    |              |              |

  coder        reviewer        Codex

implementation validation troubleshooting

                   |

                Repository

            git / tests / docs


---

# 3. Core Principle


Hermes DevOS is not an uncontrolled autonomous programmer.

It is an automated engineering coordinator.

Every task must follow:


Plan

↓

Execute

↓

Validate

↓

Report



---

# 4. Night Schedule


## 23:10 Start


Actions:

- activate DevOS scheduler
- check pending tasks
- inspect repository status
- collect unfinished work


Input sources:

- TODO list
- GitHub issues
- failed tests
- development roadmap
- previous execution reports


---

# 5. Task Discovery Phase


Time:


23:10 - 23:30



DevOS performs:


## Repository inspection

Check:


git status

git branch

recent commits

test failures

TODO markers



## Task classification


Tasks are divided into:


### Development

Send to:


coder



Examples:

- implement feature
- add tests
- refactor code


---

### Review

Send to:


reviewer



Examples:

- architecture validation
- security check
- release review


---

### Escalation

Send to:


Codex



Examples:

- repeated failure
- unknown error
- architecture conflict


---

# 6. Execution Phase


Time:


23:30 - 08:30



## coder workflow


For each task:


1. Read repository context

2. Analyze existing design

3. Modify minimum required files

4. Run tests

5. Generate completion report


Report:


```yaml
status:

changes:

tests:

risks:

next_action:
7. Review Gate

Every medium/high risk change requires reviewer.

Review checks:

correctness
regression
security
maintainability
test coverage

Result:

APPROVED

or

REQUEST_CHANGES
8. Automatic Permission Rules
Allowed

Automatic execution:

documentation update
test addition
small bug fix
code formatting
non-breaking refactoring
Require Review
API changes
database changes
dependency updates
architecture changes
Forbidden

Never execute automatically:

delete production data
modify payment logic
change security permissions
expose secrets
destructive commands
9. Codex Escalation

Codex is an emergency engineering resource.

Trigger:

coder failure >= 2 times

or

architecture uncertainty

or

critical debugging

Workflow:

coder

↓

devos

↓

Codex

↓

reviewer
10. Morning Report

Time:

08:30 - 09:00

Generate:

Development Summary

Include:

completed tasks
changed files
test results
unresolved problems
Repository Status

Include:

git status
branch information
pending changes
Next Action

Provide:

recommended next tasks
human approval items
11. Human Control

Human remains final authority.

Automatic workflow must stop when:

requirements unclear
risk classification uncertain
production impact possible
12. Future Extension

Future versions may integrate:

VPS Hermes remote workers
multi-machine execution
automatic issue creation
CI/CD integration
knowledge base feedback loop
Summary

Hermes Night AutoDev provides:

Low-cost execution window

+

Local AI orchestration

+

Specialized workers

+

Review gates

+

Human supervision

The goal is not replacing developers.

The goal is creating an AI engineering operating system.
