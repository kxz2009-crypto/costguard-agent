# Hermes DevOS Runtime Structure v0.1


## 1. Purpose

Define the fixed runtime directory structure of Hermes DevOS.


The structure is infrastructure level and independent from any single repository.


---

# 2. Root Directory

~/.hermes/



---

# 3. Runtime Layout



~/.hermes/

├── profiles/

├── scripts/
│ └── devos/
│ ├── night-autodev.sh
│ ├── collect_tasks.py
│ ├── task_state.py
│ ├── report.py
│ └── config.yaml

├── state/
│ └── autodev/

├── logs/
│ └── night-autodev/

└── reports/
└── night-autodev/



---

# 4. Directory Responsibility


## scripts

Executable automation logic.


## state

Persistent execution state.


## logs

Raw execution logs.


## reports

Human readable summaries.


---

# 5. Design Rules


Runtime code must not be stored inside project repositories.


Projects only provide:

- specifications
- requirements
- source code


Hermes DevOS remains a shared infrastructure layer.
