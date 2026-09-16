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

# CostGuard Split P1E-01 Offline HTML Report Rendering Gate v0.1

## Status and authority

**Status: PROPOSAL / DESIGN ONLY — OWNER APPROVAL PENDING.**

This document proposes the first P1E slice. It does not open the gate and does
not authorize implementation. **PRODUCT CODING IS NOT AUTHORIZED.** No source,
test, configuration, dependency, migration, release, deployment, or frozen
contract change may begin until the owner explicitly approves this gate, its
file boundary, its test requirements, and the companion implementation plan.
Reviewer validation is advisory and does not substitute for owner approval.

## Baseline and freeze point

- Frozen product baseline: `v0.8.0-p1d04-final`
- Frozen commit: `34586686cf2080d3a38600f91e33861877c97e42`
- Freeze record: `docs/gates/P1D_04_FREEZE_RECORD.md`
- Freeze state: local code freeze; release/approval record remains owner-pending
- P1E state at baseline: undefined, not implemented, and not exposed

This proposal is additive above that baseline. It grants no authority to alter
P1D-04 routes, query semantics, response shapes, error bodies, tenant guard,
time-window rules, cache policy, service parity, hashes, or prior P1 contracts.

## Proposed classification and rationale

**P1E-01 = Offline HTML Report Rendering (proposed).**

The lowest-risk next capability is a pure presentation adapter that converts an
existing P1D-03 `ReportDocument` into one deterministic, self-contained HTML
string for local/offline viewing.

Repository evidence supporting this choice:

- The roadmap ends the non-commercial P1 product-consumption layer after
  export, dashboard, report, and consumption API; every later named layer is
  independently gated P2, P3, or P4 scope.
- P1D-03 explicitly deferred HTML rendering while establishing deterministic
  `ReportDocument` output and caller-owned I/O.
- P1D-04 explicitly returns report JSON and excludes HTML rendering.
- The separate legacy `costguard_agent/html_report.py` demonstrates an existing
  local, self-contained, inline-CSS, no-script, no-network HTML precedent.
- A pure renderer can consume the frozen report DTO without database, HTTP,
  identity, ingestion, pricing, migration, authentication, or dependency work.

This proposal does not redefine the roadmap. The owner must approve both the
P1E designation and this slice before it becomes planned product scope.

## Objective

Provide a deterministic, safe, offline-viewable HTML representation of an
already-produced P1D-03 report document, without changing how analytics are
calculated, selected, authorized, transported, stored, or exposed.

For identical `ReportDocument.to_dict()` input, the renderer must return
byte-identical UTF-8-compatible HTML text. The returned document must be
self-contained and suitable for a caller to save or display locally; the
renderer itself performs no file or network I/O.

## Allowed scope

If separately approved for coding, this gate permits only:

- one pure rendering module under a new Split presentation package;
- rendering the existing report `meta`, `content_hash`, and Markdown `body`;
- a fixed document title written as static markup, a compact metadata section,
  and an escaped report body;
- inline static CSS needed for readable local display;
- semantic HTML document structure and basic accessibility labels;
- deterministic output with no current-time or environment-derived fields;
- HTML escaping of every value originating in the report document;
- one focused test module using constructed `ReportDocument` instances;
- standard-library functionality only.

The minimum safe rendering contract is deliberately narrow:

1. Input is an existing `costguard_split.report.dto.ReportDocument`.
2. Output is a complete HTML string beginning with a doctype.
3. Report body is rendered as escaped text in a presentation container; this
   slice does not introduce a general Markdown parser or raw-HTML passthrough.
4. `None` metadata values use a fixed non-sensitive display marker.
5. The renderer does not validate, recalculate, or replace the existing
   `content_hash`; it displays the frozen document value unchanged.
6. No save/download route, filename policy, or browser launch is included.

## Forbidden scope

This gate explicitly excludes and does not authorize:

- **P2:** billing, subscription, payment, pricing-engine expansion, quota,
  settlement, tenant-commercial work, commercial metering, or entitlements;
- **P3:** intelligence, recommendations, optimization, forecasting, anomaly
  detection, AI explanation, assistant behavior, or automated analysis;
- **P4:** enterprise tenancy expansion, RBAC, SSO, compliance, enterprise audit
  expansion, multi-region, or enterprise deployment;
- public internet exposure, hosting, serving, publishing, upload, external
  assets, CDN use, telemetry, tracking, or outbound network requests;
- authentication, authorization-system changes, API keys, tokens, passwords,
  cookies, credentials, secrets, secret storage, or secret configuration;
- database access, SQL, schema changes, destructive or non-destructive
  migrations, caches, materialized views, or persistence;
- prompt, response, conversation, source-code, document, file-path, credential,
  private-log, or private commercial-intelligence collection or rendering;
- new analytics, aggregation, calculation, interpretation, sorting, filtering,
  recommendations, or business decisions;
- scripts, JavaScript, active content, remote fonts, external stylesheets,
  images, iframes, forms, links to network resources, or raw HTML injection;
- filesystem writes, downloads, browser launching, email, webhook, scheduling,
  delivery, PDF generation, templates, themes, localization, or chart images;
- HTTP routes, FastAPI registration, OpenAPI changes, middleware, or changes to
  the P1D-04 consumption namespace;
- dependencies, packaging changes, configuration changes, or feature flags;
- reuse, import, modification, or unification of the legacy
  `costguard_agent/html_report.py` path in this slice;
- any change to frozen P1D-04 contracts or prior P1 modules unless separately
  proposed and explicitly authorized by the owner.

## Architecture boundary

Allowed call chain:

```text
caller with an existing ReportDocument
                |
                v
costguard_split.presentation.html_report.render_report_html
                |
                v
self-contained HTML string returned to caller
```

Forbidden call chains:

```text
renderer -> database / usage_events / SQL
renderer -> analytics / timeseries / visualization / dashboard services
renderer -> HTTP router / server context / authentication
renderer -> filesystem / subprocess / browser / network
renderer -> pricing / commercial / intelligence / enterprise layers
```

The renderer receives no database handle, organization selector, request,
server context, path, URL, credential, or callback. It must not import service,
API, connector, database, ingestion, identity, pricing, or legacy-agent
modules. Caller-owned I/O remains outside the proposed boundary.

## Data, security, and privacy boundaries

- Data minimization: render only fields already present in `ReportDocument`;
  accept no arbitrary context or extension payload.
- Input trust: treat the actual dynamic `ReportDocument` fields (`meta`, its
  filters, `body`, and `content_hash`) as untrusted text; escape all
  interpolated values, including quotes and angle brackets. The HTML document
  title is fixed static markup and is not a `ReportDocument` field.
- Active-content ban: output contains no `<script>`, event-handler attributes,
  form controls, iframe/object/embed elements, refresh directives, or external
  resource references.
- Network ban: output contains no fetch-capable markup or CSS construct,
  including external `src`/`href` attributes, stylesheet or font imports, CSS
  `url(...)`, form actions, refresh targets, or equivalent network-bearing
  constructs. URL-looking strings are permitted solely when they originate in
  report data and remain escaped, inert report text. The renderer performs no
  network I/O.
- Privacy: do not add raw usage events or any material not already in the report
  DTO. Tests must use synthetic non-sensitive data and temporary/in-memory
  objects only.
- Integrity: display the existing `content_hash` exactly; do not claim the HTML
  itself is covered by that hash and do not create a competing integrity field.
- Determinism: no clock, random value, hostname, process state, environment,
  locale, absolute path, or generated-at timestamp may affect output.
- Storage: renderer returns text only and creates no file or directory.

## Proposed file boundary

### Availability and packaging decision required

Before product coding, the owner must select exactly one availability model:

- **A — Source-tree/internal-only:** P1E-01 is callable only from the repository
  source tree. Packaging and installability are excluded, and neither this gate
  nor its implementation may imply that the renderer is available from an
  installed `costguard-agent` distribution. The addition-only file boundary
  below remains eligible for separate coding authorization.
- **B — Distributable:** P1E-01 must be available from an installed
  distribution. The current gate and file boundary are then insufficient;
  before any coding, a revised gate must explicitly authorize the necessary
  package-metadata/file-boundary change and define separate install/build
  verification. That revision and its product coding still require explicit
  owner approval.

The proposal does not choose A or B. An absent or ambiguous owner decision is
a stop condition; packaging must never be changed or inferred implicitly.

Allowed additions after explicit owner coding authorization:

- `costguard_split/presentation/__init__.py`
- `costguard_split/presentation/html_report.py`
- `tests/split_p1e01_offline_html_report_test.py`

Allowed modifications: **none**.

In particular, do not modify:

- `costguard_split/report/*`
- `costguard_split/api/*`
- `costguard_split/analytics/*`
- `costguard_split/dashboard/*`
- `costguard_split/export/*`
- `costguard_split/visualization/*`
- `costguard_split/ingest/*`
- `costguard_split/connectors/*`
- `costguard_split/identity/*`
- `costguard_agent/*`
- schemas, migrations, configuration, dependencies, packaging, or existing tests

If implementation cannot satisfy the capability entirely inside the three
allowed additions, work must stop and return to owner decision; the boundary
must not be widened implicitly.

## Required tests

| ID | Gate requirement |
|---|---|
| E1 | Complete HTML document is returned for a synthetic `ReportDocument` |
| E2 | Identical input produces byte-identical output across repeated calls |
| E3 | No clock, random, environment, host, locale, or path value appears |
| E4 | Meta window, granularity, filters, baseline, schema version, body, and existing hash are represented without recalculation |
| E5 | All untrusted metadata and body values are escaped; executable markup supplied as data cannot execute or survive as markup |
| E6 | Output contains no scripts, inline event handlers, forms, iframes, object/embed elements, or refresh directives |
| E7 | Parsed/structurally inspected output contains no fetch-capable markup or CSS construct: external `src`/`href`, stylesheet/font imports, CSS `url(...)`, form action, refresh target, or equivalent network-bearing construct. URL-looking report values are allowed only as escaped inert text |
| E8 | Rendering performs no filesystem write and creates no files |
| E9 | Rendering performs no database, service, subprocess, browser, or network call |
| E10 | Module imports stay inside stdlib plus `costguard_split.report.dto`; forbidden-layer imports and SQL tokens are absent |
| E11 | Existing `ReportDocument` and its nested data are unchanged after rendering |
| E12 | `None`, empty body, Unicode, and hostile provider/model/member/device strings render deterministically and safely |
| E13 | Existing content hash is displayed exactly and the output does not claim that it hashes the HTML |
| E14 | No P1D-04 route or prior contract is needed or changed; focused prior report and consumption regressions remain green |
| E15 | Whole product suite is green before acceptance via `scripts/run_tests.sh` |
| E16 | The owner-selected availability model is enforced: A has no packaging/installability change or installed-package claim; B has an approved revised boundary plus separately authorized package metadata and install/build tests before coding |

Tests must not touch a real CostGuard home, credentials, private logs, or
network. Static source checks supplement behavioral tests; they do not replace
them.

## Acceptance and exit criteria

The proposal may exit design review only when:

1. Reviewer confirms rationale, boundary, threat model, test traceability, and
   consistency with the frozen baseline.
2. Owner explicitly decides the open questions below and approves the P1E-01
   designation, gate, file boundary, and required tests.
3. Owner separately authorizes product coding. Approval of this draft alone is
   not coding authorization unless the owner states that explicitly.

A future implementation may be accepted only when:

- the owner has selected availability model A or B, and implementation follows
  only the corresponding approved boundary;
- under A, work stays inside the three approved additions and acceptance makes
  no installed-package availability claim;
- under B, this version of the gate cannot authorize implementation; a revised
  gate/file boundary and separately authorized packaging metadata and
  install/build tests must govern the work;
- E1-E16 pass with evidence under the selected, approved model;
- focused report and consumption regressions pass unchanged;
- the whole suite passes;
- reviewer performs boundary/security validation;
- owner signs off on acceptance;
- documentation approval and implementation are separate commits, with the
  documentation commit preceding the implementation commit;
- any release/tag/push/deploy remains separately authorized after acceptance.

No release tag or version number is proposed by this design.

## Open questions and owner decisions

1. **P1E designation:** Approve P1E-01 as the next non-commercial,
   non-intelligence, non-enterprise phase, or choose another capability?
2. **Presentation target:** Approve `ReportDocument` as the sole input rather
   than `DashboardPayload` or `ExportDocument`?
3. **Rendering depth:** Approve escaped preformatted report content as the
   initial low-risk contract, with general Markdown/table parsing deferred?
4. **File boundary:** Approve exactly the two presentation modules and one new
   test module, with no existing-file modifications?
5. **Security posture:** Approve the strict no-script/no-link/no-external-assets
   output policy and no raw-HTML passthrough?
6. **Regression scope:** Confirm focused P1D-03/P1D-04 tests plus the whole suite
   are required before acceptance?
7. **Availability/packaging:** Choose A, source-tree/internal-only with
   packaging/installability excluded and no installed-package availability
   implication, or B, distributable with a revised gate/file boundary and
   separately authorized package-metadata and install/build work before coding?
8. **Authorization:** After reviewer validation and the availability decision,
   will the owner authorize a separate implementation task, or keep P1E-01
   design-only?
