# Hermes Runtime Profile Specification v0.1


# Objective


Define executable role profiles for Local Hermes DevOS.


Profiles determine:

- responsibility
- routing
- permissions
- escalation rules



# Profile Architecture



Local Hermes


    |

    +----------------+

    |                |

Developer        Reviewer

Profile          Profile


    |

Research Profile



# Profile Types



## 1. Dev Profile


Purpose:


Software implementation.


Primary executor:


Codex


Secondary reasoning:


GLM-5.3-Flash


Tasks:


- coding
- refactoring
- tests
- git operations



Permissions:


Allowed:

- repository write
- shell execution
- git commit


Forbidden:

- production deployment
- credential access



# 2. Review Profile


Purpose:


Quality control.


Primary models:


GLM-5.3

Kimi K3


Tasks:


- architecture review
- code review
- security review
- specification checking



Permissions:


Read only.



# 3. Research Profile


Purpose:


Long-context analysis.


Primary models:


GLM-5.3-Flash

GPT-5.6

DeepSeek



Tasks:


- literature analysis
- design documents
- architecture planning



# Model Priority



Default reasoning:


1. GLM-5.3-Flash

2. GLM-5.3

3. Kimi K3

4. GPT-5.6

5. DeepSeek



Coding:


Codex first.



Troubleshooting:


Priority:


1. Codex

2. GLM-5.3

3. Kimi K3



# Escalation Rules



Normal task:


Local Hermes

    ->

Profile

    ->

Execution



Failure:


Executor failure


    ->


Reasoning model diagnosis


    ->


Retry



Repeated failure:


Escalate to VPS Hermes validation.



# Resource Policy



High token tasks:


Use local/off-peak window.



Low latency tasks:


Use fast model.



Critical decisions:


Use strongest reasoning model.



# Night Automation Binding



Time window:


23:10 - 09:00

Asia/Shanghai



Allowed:


- documentation generation
- test generation
- refactoring
- repository analysis



Forbidden:


- destructive operation
- production deployment
- credential changes



# Logging



Every task records:


task_id

profile

model

start_time

end_time

result

git_commit

tests



# Principle



Profile decides role.

Router decides model.

Executor changes code.

Reviewer approves.



