
Hermes VPS Worker Protocol v0.1
1. Purpose

Define communication between local Hermes and remote VPS Hermes.

2. Architecture
Local Hermes

(Control Plane)

      |

      |

VPS Hermes

(Compute Worker)
3. Local Responsibilities

Local Hermes:

task planning
routing
approval
aggregation
4. VPS Responsibilities

VPS Hermes:

execute assigned tasks
run heavy workloads
return results
5. Task Exchange

Request:

task_id:

objective:

context:

constraints:

expected_output:

Response:

status:

result:

logs:

artifacts:

next_action:
Principle

Local controls.

Remote computes.
