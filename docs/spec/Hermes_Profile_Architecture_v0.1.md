# Hermes Profile Architecture v0.1


## Objective

Define multi-profile architecture for local Hermes DevOS.

Local Hermes acts as task scheduler and agent coordinator.

The system uses separated profiles with clear responsibility boundaries.


# Architecture


                    Local Hermes

                         |

        ----------------------------------

        |                |               |

    hermes-dev       hermes-ops     hermes-verify

    execution        planning       validation


# Profile: hermes-dev


Purpose:

Engineering execution.


Primary executor:

Codex


Responsibilities:

- code implementation
- repository modification
- shell execution
- git operation
- debugging
- test fixing


Forbidden:

- long documentation generation
- architecture brainstorming
- literature analysis
- general research



# Profile: hermes-ops


Purpose:

Technical planning and reasoning.


Primary models:

1. GLM-5.3-Flash
2. GLM-5.3
3. Kimi K3
4. GPT-5.6
5. DeepSeek


Responsibilities:

- requirement analysis
- architecture design
- implementation plan
- test plan
- documentation
- code review preparation



# Profile: hermes-verify


Purpose:

Independent validation.


Execution node:

VPS Hermes


Responsibilities:

- testing
- security review
- regression checking
- acceptance verification



# Principle


Planning and reasoning are separated from execution.

Codex is reserved for high-value engineering tasks.

