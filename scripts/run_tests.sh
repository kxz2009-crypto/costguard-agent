#!/usr/bin/env bash
# Run from any directory using the existing project venv and no inherited secrets.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
test -x .venv/bin/python
test_home=$(mktemp -d)
trap '.venv/bin/python -c '\''import shutil, sys; shutil.rmtree(sys.argv[1])'\'' "$test_home"' EXIT
clean_env=(env -i "PATH=$PWD/.venv/bin:/usr/bin:/bin" "HOME=$test_home" TZ=UTC PYTHONUTF8=1)
# Fail early instead of silently skipping HTTP tests when dependencies are missing.
"${clean_env[@]}" .venv/bin/python -c 'import fastapi, httpx, pydantic; assert int(pydantic.__version__.split(".")[0]) >= 2'
status=0
"${clean_env[@]}" .venv/bin/python -m pytest tests/ -v || status=1
# This legacy script accumulates results; pytest alone does not assert them.
"${clean_env[@]}" .venv/bin/python tests/contract_test.py || status=1
exit "$status"
