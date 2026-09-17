# P1E-01 revision B — owner-authorized distributable implementation

## Current authority (2026-09-13)

The owner selected option 1 in this task: continue implementing the installable
P1E offline HTML report and update the gate/plan accordingly. This authorizes
coding and tests for the minimal renderer described below. It does not authorize
commits, releases, deployments, authentication work or richer rendering.

This revision supersedes the historical approval/availability/commit prerequisites
in the archived v0.1 text below. Its E1-E15 rendering and security requirements
remain applicable. Earlier document-review PASS applies only to v0.1; this
revision and implementation do not inherit an independent reviewer PASS.

## Approved model B boundary and verification

Add presentation/__init__.py, presentation/html_report.py under costguard_split,
and tests/split_p1e01_offline_html_report_test.py. Modify only this gate, its plan,
the current-status roadmap and scripts/verify_split_install.py for P1E.
The preceding authorized packaging repair already discovers costguard_split*;
no additional package metadata or dependency change is necessary for P1E.
The repaired, uncommitted working tree is the baseline, above HEAD 08e8a84.
Prior guard/packaging repairs remain a separate change set in the work report.

E16 now requires wheel and sdist-rebuilt-wheel checks that import the installed
renderer, render a synthetic report and confirm all CostGuard imports resolve
to the installation target. Base rendering must require only the standard
library. No claim of source-only availability is permitted.

## Execution and acceptance

1. Add focused E1-E13 tests and demonstrate failures before implementation.
2. Implement only render_report_html(ReportDocument) -> str and its package.
3. Verify hostile input, deterministic output, no mutation and no I/O.
4. Run unchanged P1D-03/P1D-04 tests and scripts/run_tests.sh; report skips.
5. Build/install wheel and sdist-rebuilt wheel and run E16 checks.
6. Record exact changes and evidence; independent review and owner acceptance
   remain distinct from test completion. No clean-tree or release PASS is claimed.

The owner prohibition on commits takes precedence over the historical docs-first
commit sequence. Keep all work uncommitted and distinguish documentation and
product changes in the report. No frozen report/analytics/API module is modified
for P1E. Rendering stays escaped preformatted text with fixed metadata, inline
static CSS, no scripts, links, network, filesystem, database or service access.

---

## Archived v0.1 proposal (superseded authority and packaging assumptions)

# CostGuard Split P1E-01 Offline HTML Report Rendering Implementation Plan v0.1

## Status

**PROPOSED PLAN — OWNER APPROVAL PENDING. PRODUCT CODING IS NOT AUTHORIZED.**

Gate: `docs/gates/P1E_01_OFFLINE_HTML_REPORT_RENDERING_GATE.md`

This plan is a review artifact only. It describes a possible implementation
after owner approval; it does not imply that the gate is open or that coding,
testing changes, commits, releases, or deployment are approved. Any future
worker must re-check the approved gate and repository state before acting.

## Baseline and goal

- Frozen baseline: `v0.8.0-p1d04-final`
- Frozen commit: `34586686cf2080d3a38600f91e33861877c97e42`
- Goal, if authorized: add a pure standard-library renderer that accepts an
  existing P1D-03 `ReportDocument` and returns deterministic, escaped,
  self-contained offline HTML without I/O or changes to frozen contracts.

## Approval sequence and commit separation

The required sequence is:

1. Reviewer validates this gate and plan; findings are resolved in docs only.
2. Owner decides every gate open question, including availability model A or B,
   and approves or rejects the proposal.
3. If approved, gate/plan documentation is committed as a docs-only commit.
4. Owner gives a separate explicit product-coding authorization.
5. Implementation and its new tests are developed inside the approved boundary.
6. Reviewer validates tests, security, privacy, and boundary evidence.
7. Owner signs off on implementation acceptance.
8. Implementation is committed separately from the docs commit only if commit
   authorization is explicit.
9. Release, tag, push, merge, deployment, and service operations require later,
   separate authorization.

The future docs commit and implementation commit must never be combined. This
current planning task performs neither commit.

## Approved boundary required before execution

Proposed additions only:

- `costguard_split/presentation/__init__.py`
- `costguard_split/presentation/html_report.py`
- `tests/split_p1e01_offline_html_report_test.py`

Proposed modifications: none.

If any existing file, dependency, configuration, package manifest, route,
schema, migration, or frozen P1D-04 contract appears necessary, stop before
editing and return to reviewer and owner for a revised gate.

This three-addition boundary is executable only if the owner selects gate
availability model A (source-tree/internal-only). It excludes packaging and
installability and must not imply installed-package availability. If the owner
selects model B (distributable), stop: this plan and gate must first be revised
to authorize package metadata/file-boundary changes and separate install/build
tests. Neither branch authorizes coding by itself.

## Gate-to-plan traceability

| Plan task | Gate tests / boundary traced |
|---|---|
| T0 Approval, availability decision, and baseline revalidation | Status/authority, baseline, open questions, E16 |
| T1 Add failing deterministic/render-shape tests | E1-E4, E11-E13 |
| T2 Add failing security/privacy/I/O tests | E5-E10, E12-E13 |
| T3 Add the minimal presentation package and renderer | Allowed scope, architecture, data/security/privacy boundary, E1-E13 |
| T4 Run focused P1E tests and inspect boundary | E1-E13 |
| T5 Run unchanged P1D-03/P1D-04 regressions | E14, frozen-contract boundary |
| T6 Run whole suite and inspect repository diff | E15-E16, file boundary, exit criteria |
| T7 Reviewer and owner acceptance | E16, acceptance/exit criteria and sign-off points |

No proposed implementation step is untraced, and no test may silently broaden
the gate.

## T0 — Approval and baseline revalidation

**Authorization required:** reviewer validation, then owner approval of the
gate, plan, file boundary, required tests, an explicit availability-model
decision, and a separate instruction that product coding may begin.

After authorization, before creating source or tests:

1. Read the approved gate and plan in full.
2. Verify `HEAD`, the frozen tag target, branch, status, tracked diff, and all
   untracked paths.
3. Confirm the implementation starts from the owner-approved baseline or from
   a specifically approved descendant.
4. Confirm no applicable `DECISIONS.md` has appeared; if one exists, stop for
   reconciliation rather than guessing.
5. Confirm the three proposed files do not already exist and no existing file
   needs modification.
6. Record whether the owner selected A (source-tree/internal-only) or B
   (distributable), plus the approval reference, in the work report rather than
   source code.
7. For A, confirm packaging/installability remains excluded and make no claim
   about installed-package availability. For B, stop until a revised approved
   gate/plan explicitly includes package metadata and install/build tests.

Suggested read-only commands:

```text
git status --short --branch
git diff --name-status
git rev-parse HEAD
git rev-list -n 1 v0.8.0-p1d04-final
git ls-files '*DECISIONS.md' '*decisions.md'
```

**Stop condition:** any baseline mismatch, pre-existing conflicting change,
required boundary expansion, unresolved owner decision, absent/ambiguous
availability choice, or model B without a revised approved gate and separately
authorized packaging boundary.

## Focused-test command and clean environment

Read-only inspection confirms `scripts/run_tests.sh` ignores arguments: it
always runs `pytest tests/ -v` and then `tests/contract_test.py`. Therefore it
is reserved below for E15 whole-suite validation. For genuine focused pytest
runs, use this command shape from the repository root; it reproduces the
runner's clean environment, temporary HOME, dependency preflight, interpreter,
timezone, and UTF-8 setup without modifying the runner:

```bash
run_clean_focused() (
  set -euo pipefail
  test_home=$(mktemp -d)
  trap '.venv/bin/python -c '\''import shutil, sys; shutil.rmtree(sys.argv[1])'\'' "$test_home"' EXIT
  clean_env=(env -i "PATH=$PWD/.venv/bin:/usr/bin:/bin" "HOME=$test_home" TZ=UTC PYTHONUTF8=1)
  "${clean_env[@]}" .venv/bin/python -c 'import fastapi, httpx, pydantic; assert int(pydantic.__version__.split(".")[0]) >= 2'
  "${clean_env[@]}" .venv/bin/python -m pytest "$1" -v
)
```

After defining the function in the current repository-root shell, invoke it as
`run_clean_focused <test-file-or-node>`. Its subshell gives every invocation a
fresh temporary HOME and cleans that HOME on exit.

## T1 — Specify deterministic rendering behavior with failing tests

**Create only:** `tests/split_p1e01_offline_html_report_test.py`

Using synthetic `ReportMeta` and `ReportDocument` objects, add focused tests
that initially fail because the renderer does not exist:

- E1: output is a string containing doctype, html/head/body, a fixed static
  markup title (not a dynamic `ReportDocument` field), metadata section,
  content-hash label, and report-content container.
- E2: two calls with the same object are byte-identical.
- E3: patch or sentinel-check time/random/environment access and assert output
  contains no generated timestamp, hostname, absolute path, or locale value.
- E4: assert schema version, baseline, window, granularity, each filter, body,
  and hash are represented without changing the source values.
- E11: deep-snapshot `document.to_dict()` before rendering and compare after.
- E12: cover empty body, Unicode, and every nullable metadata field.
- E13: assert the existing hash is shown verbatim and no label claims it hashes
  the rendered HTML.

Run
`run_clean_focused tests/split_p1e01_offline_html_report_test.py`. To keep RED
feasible, do not import the absent module at test-module scope. Defer the
`importlib.import_module("costguard_split.presentation.html_report")` call to a
test/helper invocation so pytest collection succeeds and the test fails during
execution with `ModuleNotFoundError`. Do not assert that the import failure is
expected, because that would make RED pass, and do not weaken assertions.

Reviewer checkpoint: confirm tests encode the gate rather than an unapproved
richer HTML/Markdown feature.

## T2 — Specify security, privacy, and side-effect boundaries with failing tests

**Continue only in:** `tests/split_p1e01_offline_html_report_test.py`

Add synthetic hostile values independently to body, baseline, window,
granularity, and every filter. Trace requirements as follows:

- E5: angle brackets, quotes, ampersands, script fragments, and handler
  fragments appear only escaped as text.
- E6: parse or inspect output to ensure no script, form, iframe, object, embed,
  meta-refresh, or event-handler attribute is emitted.
- E7: parse the output (for example with stdlib `html.parser`) and structurally
  inspect element attributes and style text for external `src`/`href`,
  stylesheet/font imports, CSS `url(...)`, form action, refresh target, and
  equivalent fetch-capable constructs. Include `http://`, `https://`, and `//`
  in hostile report values and prove they survive only as escaped, inert report
  text; do not reject these substrings globally.
- E8: run in an isolated temporary directory and assert its recursive contents
  are unchanged before and after rendering; patch common write/open paths where
  useful without relying only on mocks.
- E9: deny or sentinel-patch network, subprocess, browser, and database entry
  points; rendering must complete without touching them.
- E10: inspect the new module source/AST for imports outside stdlib and
  `costguard_split.report.dto`, and for SQL or forbidden-layer references.
- E12: combine Unicode and hostile provider/model/member/device values.
- E13: include a hash-looking hostile string and verify escaping plus exact text
  preservation.

Run `run_clean_focused tests/split_p1e01_offline_html_report_test.py`. Expected
pre-implementation result remains collected tests failing during execution
because the renderer module is absent, not a pytest collection or fixture
error.

Security reviewer checkpoint: approve escaping assertions, active-content ban,
network ban, and real no-write evidence before implementation proceeds.

## T3 — Implement the minimum approved renderer

**Create only:**

- `costguard_split/presentation/__init__.py`
- `costguard_split/presentation/html_report.py`

Implementation constraints:

1. Export one narrow public function, proposed as
   `render_report_html(document: ReportDocument) -> str`.
2. Use only standard-library HTML escaping and the existing report DTO type.
3. Build a fixed complete HTML document with inline static CSS.
4. Escape every dynamic value at interpolation time, including the report body
   and content hash; do not support raw HTML.
5. Render the body as escaped preformatted text. Do not implement Markdown
   parsing, tables, links, templating, themes, charts, JavaScript, or assets.
6. Use a fixed marker for `None`; do not omit fields based on truthiness.
7. Preserve input order and values; do not sort, calculate, interpret, validate,
   mutate, or regenerate the report or its hash.
8. Read no time, environment, host, locale, filesystem, database, network, or
   process state.
9. Accept no path, URL, database, context, request, organization selector,
   callback, arbitrary mapping, or extension payload.
10. Add no compatibility coupling to `costguard_agent/html_report.py`.

Run the clean focused-test command for the P1E test file after the minimal
implementation. Expected: E1-E13 pass. If satisfying a test requires an
existing-file edit or richer behavior, stop and return to owner decision.

Implementation reviewer checkpoint: inspect the full two-file source boundary
before regression testing.

## T4 — Focused P1E verification and boundary inspection

Run `run_clean_focused tests/split_p1e01_offline_html_report_test.py`.
Then perform read-only checks that:

- only the three approved implementation/test files changed relative to the
  approved docs baseline;
- no tracked file outside that boundary changed;
- the renderer has no forbidden import, SQL, I/O, network, active-content, or
  nondeterministic source path;
- tests use only synthetic values and temporary paths;
- E1-E13 each map to at least one test assertion.

Do not use a passing static keyword scan as the sole proof of security or
side-effect freedom; retain behavioral checks from T2.

Reviewer sign-off point: focused behavior and boundary must be green before
running broader regressions.

## T5 — Frozen P1 regression verification

Without editing existing tests, run each focused prior suite with a fresh
invocation of the clean focused-test command:

- `run_clean_focused tests/split_p1d03_report_test.py`
- `run_clean_focused tests/split_p1d04_consumption_api_test.py`

This traces E14. Confirm prior report DTO/body/hash behavior and P1D-04 endpoint
contracts remain unchanged. Any failure is a blocker; do not modify frozen
modules or prior tests to accommodate P1E.

Reviewer sign-off point: confirm failures, skips, retries, and environment facts
are reported exactly and no baseline regression is waived.

## T6 — Whole-suite and repository-scope verification

Run the whole product suite with `scripts/run_tests.sh`, not an improvised
subset. This traces E15. Record pass/fail/skip/retry totals exactly from real
output.

Then inspect:

```text
git status --short --branch
git diff --name-status <approved-docs-baseline>
git diff --check
git diff --stat
```

Before any authorized implementation commit, verify the implementation diff
contains only the three approved additions and no docs modification. The
already-approved gate and plan must reside in an earlier docs-only commit.

For E16, verify the recorded owner choice. Under A, confirm no package metadata
changed and all reports describe the renderer as source-tree/internal-only,
not installed-package functionality. Under B, do not execute this plan: require
the revised approved boundary and its separately authorized package metadata
and install/build tests.

No commit is permitted merely because tests pass. Commit only after explicit
commit authorization, with a message that identifies P1E-01. Do not tag, push,
merge, deploy, restart services, or rewrite history.

## T7 — Acceptance handoff

Prepare evidence for two distinct decisions:

**Reviewer validation:**

- gate-to-test matrix E1-E16;
- focused P1E results;
- unchanged P1D-03/P1D-04 regression results;
- whole-suite results;
- exact file list and diff summary;
- security/privacy/boundary review;
- any skips, flakes, assumptions, or deviations.

**Owner sign-off:**

- confirm availability model A or B and evidence satisfying E16;
- accept or reject the implementation;
- decide whether an implementation commit is authorized;
- separately decide any release/tag/push/merge/deploy action.

Until both checkpoints are satisfied, report the work as pending acceptance,
not completed or released.

## Risks and mitigations

- **HTML injection:** escape every dynamic field and body; hostile-value tests.
- **Misleading integrity claim:** display the existing report-body hash only and
  label it accordingly; never imply it covers HTML.
- **Scope creep into Markdown/UI framework:** initial body stays escaped and
  preformatted; richer rendering requires a new owner-approved gate amendment.
- **Privacy expansion:** accept only `ReportDocument`; add no raw events,
  extension metadata, paths, or environment details.
- **Hidden I/O/network behavior:** pure signature, import boundary, behavioral
  denial tests, and temporary-directory no-write checks.
- **P1D-04 regression:** no API or existing-file modification; focused frozen
  regression suite plus whole-suite verification.
- **Packaging ambiguity:** the current package manifest discovers only
  `costguard_agent*`. Owner must explicitly select A (source-tree/internal-only,
  with no packaging change or installed-package claim) or B (distributable,
  requiring a revised approved gate/boundary and separately authorized package
  metadata and install/build tests). Stop while undecided; never modify or
  imply packaging implicitly.

## Owner decisions required before coding

Coding remains blocked pending explicit answers to the gate's eight open
questions, especially:

- approval of P1E-01 and `ReportDocument` as the sole input;
- approval of escaped preformatted content rather than Markdown parsing;
- approval of the exact three-file addition-only boundary;
- decision on source-only/internal availability versus a separately gated
  packaging change;
- explicit product-coding authorization after reviewer validation.
