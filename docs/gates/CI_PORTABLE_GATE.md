# CostGuard Split portable CI gate

GitHub Actions runs this gate for pull requests targeting `main` and pushes to
`main`. The exact check name intended for later branch protection is:

`portable-gate`

After the first hosted run, DevOS must confirm the literal check-run name
reported by GitHub before configuring branch protection. Branch protection is
configured separately, only after this check has passed on GitHub.

## Scope

The gate uses a clean Ubuntu checkout and Python 3.12, a version supported by
`pyproject.toml`. It installs the exact dependency versions in
`requirements-ci.txt`, runs `scripts/run_tests.sh` with its isolated temporary
home, and therefore runs the full portable pytest suite plus the independent
connector contract script. It also builds the wheel and source distribution,
verifies an isolated wheel installation, rebuilds a wheel from the source
distribution, and verifies that installation with the Split server extras.

Failures in any command fail the job. Existing environmental skips remain
visible: connector contract checks that require installed, real Hermes or Codex
sources skip under the isolated home, and tests that explicitly require Git
metadata run because Actions checks out the repository. Dependency warnings
remain visible and are not suppressed. HTTPX2 is pinned only in the CI/test
stack for Starlette TestClient verification; it is not a public Split server
runtime dependency. AnyIO 4.14.2 is temporarily pinned only in CI because
Starlette 1.6.0 references the deprecated `anyio.abc.BlockingPortal` alias.
Revisit and remove that pin when Starlette uses
`anyio.from_thread.BlockingPortal` or otherwise resolves the warning.

## Known gaps

This is a portable, offline application test gate after dependency installation.
It does not read real connector state, credentials, private databases or logs;
call paid APIs or production services; deploy; or validate cloud resources.
It does not reproduce or attest to the separate local real-source 1662-event or
66-event evidence. The initial package download is the only required external
service access. Python 3.10 and 3.11 remain supported but are not a hosted CI
matrix in this minimal gate.
