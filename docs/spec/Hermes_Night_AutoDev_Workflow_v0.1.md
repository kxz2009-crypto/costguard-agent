# Hermes Night AutoDev Workflow v0.1


## Schedule


Timezone:

Asia/Shanghai


Execution window:

23:10 - 09:00


Purpose:

Use low-cost model period for autonomous development tasks.



# Workflow


## Phase 1

23:10 - 02:00


hermes-ops


Tasks:

- scan project status
- analyze backlog
- generate implementation plan
- prepare coding tasks



## Phase 2

02:00 - 06:00


Task router decides:


Documentation:

    hermes-ops


Code modification:

    hermes-dev

    Codex



## Phase 3

06:00 - 09:00


Validation:


hermes-verify


Tasks:

- run tests
- review changes
- generate report



# Safety Rules


No automatic production deployment.


All code changes require:

- git commit
- test result
- change summary



