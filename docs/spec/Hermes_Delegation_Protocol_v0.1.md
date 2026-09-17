# Hermes Delegation Protocol v0.1


## 1. Purpose

Define the communication standard between Hermes DevOS and worker agents.


---

# 2. Task Object


Every delegated task should contain:


```yaml
task_id:

objective:

context:

repository:

constraints:

assigned_worker:

expected_output:

validation_method:
Example:

task_id:
  CG-P1C03-001

objective:
  Implement cost trend export API

repository:
  costguard-core

assigned_worker:
  coder

validation_method:
  reviewer
3. Worker Execution Rules

Worker must:

inspect existing implementation
avoid unnecessary changes
follow repository rules
execute validation
provide completion report
4. Completion Report Format
status:
  completed | blocked | failed


changes:

tests:

issues:

risks:

next_action:

Example:

status:
  completed

changes:
  - added trend export endpoint

tests:
  - pytest passed

risks:
  none

next_action:
  reviewer validation
5. Escalation Protocol

When coder cannot solve:

coder

↓

devos

↓

Codex

Conditions:

repeated failure
unclear architecture
conflicting requirements
critical bug
6. Review Loop

Implementation:

coder

↓

Review:

reviewer

↓

Decision:

approve

or

return for modification

