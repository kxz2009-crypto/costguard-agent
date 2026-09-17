
Hermes Memory Strategy v0.1
1. Purpose

Define memory architecture for Hermes DevOS.

2. Three Layer Memory
Layer 1: Session Memory

Contains:

current conversation
temporary decisions
active tasks

Lifetime:

single session

Layer 2: Project Memory

Contains:

repository architecture
design decisions
known issues
historical changes

Lifetime:

project lifecycle

Layer 3: System Memory

Contains:

user preferences
routing rules
model strategy
workflow configuration

Lifetime:

long term

3. Memory Rules

Store:

reusable knowledge
decisions
lessons learned

Do not store:

temporary logs
secrets
unnecessary output
Principle

Every execution should improve future execution.
