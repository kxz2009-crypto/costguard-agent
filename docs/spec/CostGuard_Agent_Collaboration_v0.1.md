# CostGuard Agent Collaboration v0.1



# 1. Agent Topology



                 Local Hermes

                      |

        ----------------------------

        |                          |

      Codex                  VPS Hermes

   execution              independent review



# 2. Local Hermes


Role:


Project orchestration agent.



Responsibilities:


- project state management
- workflow control
- task scheduling
- agent dispatch
- memory maintenance



Not responsible:


- uncontrolled coding
- bypassing approval



# 3. Codex


Role:


Implementation executor.



Responsibilities:


- code modification
- test implementation
- debugging
- refactoring



Must follow:


Gate

↓

Plan

↓

Implementation

↓

Test



# 4. VPS Hermes


Role:


Independent reviewer.



Responsibilities:


- architecture review
- security review
- boundary verification



Restrictions:


- no direct coding
- no release authority



# 5. Communication Flow



Local Hermes

↓

Task Specification

↓

Codex

↓

Git Branch

↓

VPS Hermes

↓

Review Result

↓

Local Hermes



# 6. Final Authority


Human decides:


- architecture
- security boundary
- release
- merge
