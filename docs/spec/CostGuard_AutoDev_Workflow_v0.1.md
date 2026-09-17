# CostGuard AutoDev Workflow v0.1


# Objective


Define an automated engineering workflow for CostGuard development.


The system must guarantee:


- scope control
- boundary protection
- test verification
- release discipline



---


# Workflow


Gate

↓

Architect Agent

↓

Implementation Plan

↓

Approval

↓

Builder Agent

↓

Test Agent

↓

Boundary Review Agent

↓

Release Agent

↓

Git Tag




---


# Agent Roles



# Architect Agent


Permission:


READ ONLY


Input:


- gates
- roadmap
- existing architecture


Output:


Implementation Plan


Forbidden:


- modify source code
- commit
- release



---


# Builder Agent


Permission:


WRITE


Allowed:


Only files explicitly listed in approved plan.


Example:


Allowed:


costguard_split/analytics/*
tests/*



Forbidden:



costguard_split/identity/*
costguard_split/connectors/*
costguard_split/ingest/*



unless explicitly authorized.



---


# Test Agent


Responsibilities:


Execute:


- unit tests
- acceptance tests
- boundary tests
- keyword scanning



Required output:


TEST_REPORT.md



Example:



Tests PASS

Boundary PASS

Keyword PASS




---


# Boundary Review Agent


Check:


## File Boundary


Compare:


Approved files

vs

git diff



Failure:


Any unauthorized modification.



---


# Keyword Guard


Default forbidden capability words:



billing
quota
allocation
optimization
recommendation
forecast
anomaly




Exception:


Only when gate explicitly allows.



---


# Release Agent


Release requires:



tests = PASS

boundary = PASS

keyword = PASS

git status = clean




Only then:



git tag

git push




---


# Automated Development Directory


Recommended:



scripts/

boundary_check.py

keyword_guard.py

release_guard.py




---


# Future Hermes Skill


Location:



~/.hermes/skills/costguard-dev/




Structure:



costguard-dev/

SKILL.md

agents/

architect.md

builder.md

tester.md

reviewer.md

release.md

guards/

boundary.md

keyword.md

release.md

templates/

plan.md

review_report.md




---


# First Automated Trial


Target:


P1D-01 Analytics Export Layer



Workflow:



architect

↓

plan

↓

approval

↓

builder

↓

test

↓

review

↓

release




Goal:


Create the first fully agent-driven CostGuard release.



