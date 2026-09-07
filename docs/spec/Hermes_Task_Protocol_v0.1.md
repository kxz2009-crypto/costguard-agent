# Hermes Task Protocol v0.1


## Objective


Define standardized task handoff protocol between:

- Local Hermes
- Codex
- LLM reasoning models
- VPS Hermes


The protocol ensures reproducible autonomous workflows.



# Task Lifecycle



User Request


    |


Local Hermes


    |


Task Classification


    |


----------------------------

|            |             |

Planning   Coding     Verify


LLM        Codex      VPS Hermes



# Task Package


Every delegated task MUST contain:



## 1. Goal


Clear objective.


Example:


Implement P1C-03 dashboard read model.



## 2. Context


Required background:

- repository
- branch
- related documents
- previous commits



## 3. Scope


Allowed files:


Example:

costguard_split/dashboard/*



Forbidden files:


Example:

identity/*



## 4. Acceptance Criteria


Must include:


- tests
- expected behavior
- forbidden behavior



## 5. Output Format


Every agent MUST return:



### Summary

What changed.



### Files

Modified files.



### Tests

Executed tests and results.



### Risks

Remaining issues.



# Routing Rules



## Architecture Questions


Route:

Local Hermes

        |

LLM reasoning model



Preferred:

GLM-5.3-Flash

GLM-5.3

Kimi K3



## Coding Tasks


Route:

Local Hermes

        |

Codex



Requirements before Codex:


- implementation plan exists
- file boundary defined
- acceptance criteria defined



## Verification


Route:


VPS Hermes



Responsibilities:


- regression test
- environment validation
- security review



# Failure Handling



If Codex fails:


Do not immediately retry.


First:

1. collect error
2. send to reasoning model
3. update task context
4. retry



If tests fail:


Create debugging task.



# Git Rules



Every completed coding task requires:


git diff summary

git commit

test result



No direct push without validation.



# Principle


Hermes coordinates.

Models reason.

Codex executes.

VPS validates.



