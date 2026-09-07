# Hermes DevOS v0.2 — CostGuard Development Pipeline


## 1. Objective

Hermes DevOS v0.2 moves from passive observation to controlled autonomous development.

Primary target:
costguard-core


Goal:

Enable Hermes DevOS to discover development tasks, assign appropriate agents, execute implementation, run validation, and perform review.


---

# 2. Scope

v0.2 ONLY implements:


Task Discovery

↓

Task Routing

↓

Coder Execution

↓

Testing

↓

Reviewer Gate

↓

Result Report



Not included:

- automatic merge to main
- automatic deployment
- production modification
- unrestricted autonomous coding


---

# 3. Architecture


             Hermes DevOS

                  |

          Task Router

                  |

    --------------------------------

    |              |              |

Low Risk       Coding        Review

    |              |              |

qwen3.8      GLM-5.3-flash   GLM-5.3/K3

                  |

            coder profile

                  |

          git feature branch

                  |

                tests

                  |

               commit

                  |

            reviewer profile

                  |

          PASS / NEED_FIX


---

# 4. Model Routing


## Local Worker

Model:


qwen3.8:27B



Responsibilities:

- local batch tasks
- documentation processing
- code scanning
- low-risk maintenance
- offline tasks


---

## Coder Agent

Model:


GLM-5.3-flash



Responsibilities:

- implement CostGuard features
- modify source code
- write tests
- execute development workflow


---

## Reviewer Agent


Primary:


GLM-5.3



Advanced:


Kimi K3



Responsibilities:

- architecture review
- code quality review
- security review
- specification compliance


---

## Specialist


Model:


Codex



Only used for:

- repeated failures
- architecture conflicts
- complex debugging
- large refactoring


---

## Fallback

Model:


DeepSeek



Used when:

- primary model unavailable
- quota limitation
- service failure


---

# 5. Development Workflow


## Step 1 — Task Discovery


Sources:



docs/spec

docs/plans

TODO/FIXME

git status

roadmap



Output:


task.yaml



Example:

```yaml
project: costguard

task:
  id: P1C-03
  type: coding
  priority: high
Step 2 — Task Routing

Router decides:

documentation
        |
        qwen


coding
        |
        GLM coder


review
        |
        GLM/K3


failure
        |
        Codex
Step 3 — Coder Execution

Coder workflow:

read specification

↓

inspect repository

↓

create feature branch

↓

modify code

↓

run tests

↓

generate commit

↓

return result

Rules:

must follow repository AGENTS.md
must not modify unrelated files
must provide test evidence
Step 4 — Reviewer Gate

Reviewer checks:

Specification

Does implementation match requirement?

Code

Is implementation reasonable?

Testing

Are tests sufficient?

Risk

Could this break existing features?

Output:

PASS:

approved

or:

NEED_FIX:

issues:
 - xxx
Step 5 — Human Approval

v0.2 does not automatically merge.

Flow:

coder

↓

reviewer

↓

human approval

↓

merge
6. State Machine

Task lifecycle:

CREATED

↓

ASSIGNED

↓

CODING

↓

TESTING

↓

REVIEWING

↓

APPROVED

↓

DONE

Failure:

FAILED

↓

RETRY

↓

CODEX_ESCALATION
7. CostGuard First Tasks

Initial development tasks should come from:

docs/spec

docs/plans

P1 roadmap

No artificial tasks should be created.

8. Safety Rules

Required:

branch isolation
test verification
reviewer approval

Forbidden:

direct main modification
automatic production deployment
bypass review
9. Success Criteria

v0.2 is complete when:

Hermes can discover CostGuard tasks
coder can complete one real feature
reviewer can validate result
failure can escalate to Codex
complete execution history is recorded
Principle

v0.1:

Observe.

v0.2:

Develop under control.

v0.3:

Multi-project autonomous engineering.
