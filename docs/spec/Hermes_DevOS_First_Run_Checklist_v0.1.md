# Hermes DevOS First Run Checklist v0.1


## 1. Purpose

Define validation procedure before enabling automatic execution.


---

# 2. First Run Mode


Initial mode:



DRY RUN ONLY



No code modification allowed.


---

# 3. Validation Steps


## Environment


Check:


- Hermes profile available
- Python environment
- permissions


---

## Directory


Verify:



~/.hermes/scripts/devos

~/.hermes/state/autodev

~/.hermes/logs/night-autodev

~/.hermes/reports/night-autodev



---

## Execution


Run manually:



night-autodev.sh



Verify:


- tasks generated
- state recorded
- report created


---

# 4. Cron Enable Condition


Enable cron only after:


- three successful dry runs
- correct task detection
- valid reports


---

# 5. Upgrade Path


After validation:


Enable:



coder execution



Then:



reviewer gate



Finally:



VPS worker

