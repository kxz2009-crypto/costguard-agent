# P1D-04 Open Consumption API Gate Draft — Codex Review Record

Reviewer: Codex CLI 0.153.4 (read-only sandbox)
Reviewed: draft docs/gates/P1D_04_OPEN_CONSUMPTION_API_GATE_DRAFT.md @ baseline v0.7.0-p1d03 (d161f8c)
Verdict: AMEND-THEN-APPROVE (apply amendments 1-7; coding still requires plan/file/test approval + user sign-off)

---

**AMEND-THEN-APPROVE.** The proposed read-only adapter is appropriate for P1D-04, but the draft needs corrections to tenant enforcement, dashboard filtering, route history, and the stable contract before coding is authorized.

The baseline is correct: HEAD and `v0.7.0-p1d03` resolve to `d161f8c27f5d2df61e3161fd188ff8045a061830`. No files were modified. This was a static review; tests were not run.

I could not locate a CostGuard `DECISIONS.md` in this repository or its surrounding project directory. Consequently, compliance with that document’s conventions remains **unverified**; the authorization requirements below are supported by the available gate documents.

**A) Explicit answers to REVIEW QUESTIONS 1–3**

1. **Parallel namespace: acceptable; replacement is unnecessary.** Preserve the implemented `/api/v1/visualization/*` routes and add `/api/v1/consumption/*`. The draft incorrectly identifies the implemented namespace as `/internal/visualization/*`: that is the precedent gate’s proposed contract, but the factory mounts the adapters under `/api/v1`. See [app.py:55](/home/gao20/projects/costguard/costguard-core/costguard_split/api/app.py:55), [visualization.py:35](/home/gao20/projects/costguard/costguard-core/costguard_split/api/visualization.py:35), and [trend_visualization.py:36](/home/gao20/projects/costguard/costguard-core/costguard_split/api/trend_visualization.py:36). Replacement would introduce unrelated migration work.

2. **Pagination: deferral is acceptable for the initial internal surface, but the stated justification is false.** A supplied window is not an enforced resource bound. Neither service limits window duration or result cardinality; both load all matching events with `fetchall()`. Summary dimension lists can grow with member/device cardinality even within a short window. See [analytics/service.py:153](/home/gao20/projects/costguard/costguard-core/costguard_split/analytics/service.py:153) and [analytics/timeseries.py:88](/home/gao20/projects/costguard/costguard-core/costguard_split/analytics/timeseries.py:88). Require an explicit window policy and acknowledgment that pagination deferral does not bound query memory. Do not silently truncate aggregates or hashed documents.

3. **Rate limiting and caching may be deferred; require `Cache-Control: no-store` now.** Make the draft’s tentative position normative. Apply it to consumption success **and error** responses, including framework-generated validation errors. A header assigned only inside successful handlers will miss those responses. This is an HTTP transport policy, compatible with the prohibition on introducing a cache.

**B–C) Contradictions and required exact amendments**

The following replacement/addition text is my proposed approval condition.

**1. Classification and relationship to the precedent — amend.**

The opening incorrectly says “four existing P1D read layers” while naming three, and attributes the time-series read model to P1C-02. The read service is P1C-01; P1C-02 adds its HTTP adapter.

Replace draft lines 22–24 with:

> “If separately authorized for implementation, this gate permits HTTP consumption of existing analytics and visualization projections, the P1C-01 time-series read model, and the three P1D read layers: export, dashboard, and report. P1C-02 supplies the existing trend HTTP adapter.”

Replace the relationship bullets at lines 78–84 with:

> “The P1B-03 gate specified `/internal/visualization/*`; the implementation exposes `/api/v1/visualization/*`, including the trend route subsequently added by P1C-02. Preserve all implemented visualization routes and their contracts unchanged. Add `/api/v1/consumption/*` without aliases, replacement, or deprecation in this slice.”

The precedent explicitly deferred trend pending a time-series model: [P1B-03 gate:298](/home/gao20/projects/costguard/costguard-core/docs/gates/P1B_03_VISUALIZATION_API_GATE.md:298).

**2. Tenant isolation — amend; blocking correctness issue.**

“Same `_check_org` pattern” is insufficient: both existing guards bypass checks when `context is None`, and `create_app()` defaults to that state. See [visualization.py:24](/home/gao20/projects/costguard/costguard-core/costguard_split/api/visualization.py:24) and [app.py:44](/home/gao20/projects/costguard/costguard-core/costguard_split/api/app.py:44). Copying this behavior would contradict the draft’s mandatory authorization boundary and [context.py:4](/home/gao20/projects/costguard/costguard-core/costguard_split/api/context.py:4).

Replace the tenant requirements with:

> “Every consumption data endpoint requires an explicit `org_id` and a non-null, server-supplied `ServerContext`. Missing context or an `org_id` mismatch returns `404` with `{"detail":"not found"}` before calling any read service. Client query parameters, bodies, and headers MUST NOT create or select the authoritative context. This change applies only to consumption routes.”

Replace “unknown org / foreign org” in the error contract with:

> “Missing server context or requested organization differing from the context returns 404. A matching context organization with no matching usage returns the existing empty read-model representation. No organization-existence database lookup is introduced.”

The current read services do not validate organization existence; they filter usage rows. Equality with a context is not an existence check.

**3. Dashboard filtering — amend; blocking semantic issue.**

The draft promises summary inputs plus granularity, but `dashboard_projection()` applies filters only to summary-derived sections; trend remains organization-wide. Its metadata nevertheless echoes the filters. See [dashboard/service.py:47](/home/gao20/projects/costguard/costguard-core/costguard_split/dashboard/service.py:47) and [dashboard/service.py:62](/home/gao20/projects/costguard/costguard-core/costguard_split/dashboard/service.py:62).

For this slice, replace dashboard inputs with:

> “Required query parameters: `org_id`, `start`, `end`, and `granularity=day|hour`. Dashboard filters are not supported in this slice. Requests containing `provider`, `model`, `member_id`, or `device_id` return 422; they MUST NOT be silently ignored. The adapter calls `dashboard_projection()` without filters. Filtered dashboard trends require a separately authorized read-model change.”

This avoids modifying the forbidden analytics/dashboard layers or exposing a misleading composite.

**4. Response contract — amend.**

The DTO references are useful but incomplete:

- Dashboard serialization contains top-level `provider_distribution`, `model_distribution`, and `extra`; there is no `distributions` property. See [dashboard/dto.py:41](/home/gao20/projects/costguard/costguard-core/costguard_split/dashboard/dto.py:41).
- Distribution export also includes a visualization `summary`, beyond the two distribution lists. See [export/service.py:153](/home/gao20/projects/costguard/costguard-core/costguard_split/export/service.py:153).
- Report cost nulls become empty Markdown cells, not JSON nulls inside the body. See [report/service.py:57](/home/gao20/projects/costguard/costguard-core/costguard_split/report/service.py:57).

Add:

> “All successful consumption responses are JSON. `/distributions` returns exactly `provider_distribution` and `model_distribution`, each containing serialized `DistributionPoint` objects with `dimension`, `key`, `events`, and `tokens`. `/dashboard` returns `meta`, `totals`, `provider_distribution`, `model_distribution`, `trend`, and `extra`. Export endpoints preserve the complete existing `ExportDocument.to_dict()` output, including the distribution payload’s `summary`. Report endpoints preserve `ReportDocument.to_dict()`, with Markdown in the `body` string; no file download or HTML rendering is added.”

Add to versioning:

> “The v1 stability commitment applies only to `/api/v1/consumption/*`. It covers field names, types, nullability, query semantics, ordering semantics, and documented errors. Internal DTO changes do not automatically authorize wire-contract changes. Preserve existing document schema versions, baseline metadata, hash algorithms, and hash inputs. Success-shape requirements do not replace documented error bodies.”

This avoids retroactively granting stability to every existing `/api/v1` endpoint. The prior gate expressly excluded a backward-compatibility guarantee: [P1B-03 gate:248](/home/gao20/projects/costguard/costguard-core/docs/gates/P1B_03_VISUALIZATION_API_GATE.md:248).

**5. Time validation and pagination — amend.**

K12 has no expected behavior. Services use string comparisons for the window; ingestion normalizes timestamps to UTC. See [analytics/service.py:125](/home/gao20/projects/costguard/costguard-core/costguard_split/analytics/service.py:125) and [ingest/service.py:56](/home/gao20/projects/costguard/costguard-core/costguard_split/ingest/service.py:56).

Add this explicit proposed policy:

> “`start` and `end` must be timezone-aware ISO-8601 timestamps. Normalize them to the ingestion UTC serialization before calling services. The window is `[start,end)` and must satisfy `start < end` and a maximum duration of 31 days. Malformed, timezone-naive, reversed, empty, or oversized windows return 400. Missing required parameters return 422. Validate granularity before service invocation, including for empty datasets.”

Replace the pagination exclusion with:

> “Pagination is deferred for the initial internal surface. The window limit does not bound event or dimension cardinality, and existing services materialize matching events. Responses are complete, without silent truncation. Public or larger-scale operational exposure requires a separate resource-control review.”

The 31-day limit is a **proposed gate decision**, not an existing code constraint.

**6. Health, caching, and file boundary — amend.**

The unscoped health endpoint conflicts with “Every endpoint MUST require org_id.” The application already has `/healthz` at [app.py:57](/home/gao20/projects/costguard/costguard-core/costguard_split/api/app.py:57).

Replace the proposed consumption health endpoint with:

> “No additional health endpoint is introduced. Existing `/healthz` remains unchanged.”

Replace the tentative caching policy with:

> “Every response under `/api/v1/consumption/` MUST carry `Cache-Control: no-store`, including validation and error responses. Rate limiting, application caching, ETags, and conditional responses remain deferred.”

Clarify the allowed `app.py` modification:

> “Allow importing and invoking the consumption adapter’s registration function before `include_router()`. Any namespace-scoped response policy is implemented in `consumption.py` and installed by that function; it must not change existing routes’ behavior.”

**7. Required tests and authorization — amend.**

Repeated calls being equal do not prove schema compatibility. Row counts remaining stable do not detect updates. Add:

> “Tests must verify explicit baseline response keys/types/nullability; service-output parity; unchanged export/report hashes; missing-context rejection before service calls; organization isolation across every data endpoint; rejected dashboard filters; defined time-validation outcomes; invalid granularity with empty and populated data; and no-store headers on success and error responses. Mutation checks must detect changed row contents as well as row counts. Preserve and run both visualization API and trend API regression suites. NULL preservation follows each existing representation, including empty Markdown cost cells.”

Add to authorization requirements:

> “Before coding authorization, identify the authoritative CostGuard `DECISIONS.md` and reconcile this gate with its applicable conventions, or explicitly record that no such document applies. Reviewer approval of the amended design does not itself authorize coding; implementation-plan, file-boundary, test-plan approval, and the stated user sign-off remain required.”

**D) Roadmap scope**

Versioning and a stable consumption contract are **within** scope: [roadmap:265](/home/gao20/projects/costguard/costguard-core/docs/spec/CostGuard_Split_ROADMAP_v0.1.md:265) explicitly calls for a “Stable external consumption interface” and a separate API gate.

Clarify “external” with:

> “External consumption means consumers outside the Python modules; this slice remains internally deployed. It does not authorize public internet availability or a SaaS service commitment.”

The actual scope risks are extending stability to the entire `/api/v1` namespace, replacing legacy routes, or adding filtered time-series aggregation to fulfill the dashboard promise. The amendments above exclude those expansions. Baseline, read-only objective, architecture boundary, authentication deferral, storage exclusions, and dependency exclusions are otherwise acceptable.

**Final verdict: AMEND-THEN-APPROVE — apply amendments 1–7 above; coding remains unauthorized until the amended gate’s prerequisites are satisfied.**
tokens used
42,134
**AMEND-THEN-APPROVE.** The proposed read-only adapter is appropriate for P1D-04, but the draft needs corrections to tenant enforcement, dashboard filtering, route history, and the stable contract before coding is authorized.

The baseline is correct: HEAD and `v0.7.0-p1d03` resolve to `d161f8c27f5d2df61e3161fd188ff8045a061830`. No files were modified. This was a static review; tests were not run.

I could not locate a CostGuard `DECISIONS.md` in this repository or its surrounding project directory. Consequently, compliance with that document’s conventions remains **unverified**; the authorization requirements below are supported by the available gate documents.

**A) Explicit answers to REVIEW QUESTIONS 1–3**

1. **Parallel namespace: acceptable; replacement is unnecessary.** Preserve the implemented `/api/v1/visualization/*` routes and add `/api/v1/consumption/*`. The draft incorrectly identifies the implemented namespace as `/internal/visualization/*`: that is the precedent gate’s proposed contract, but the factory mounts the adapters under `/api/v1`. See [app.py:55](/home/gao20/projects/costguard/costguard-core/costguard_split/api/app.py:55), [visualization.py:35](/home/gao20/projects/costguard/costguard-core/costguard_split/api/visualization.py:35), and [trend_visualization.py:36](/home/gao20/projects/costguard/costguard-core/costguard_split/api/trend_visualization.py:36). Replacement would introduce unrelated migration work.

2. **Pagination: deferral is acceptable for the initial internal surface, but the stated justification is false.** A supplied window is not an enforced resource bound. Neither service limits window duration or result cardinality; both load all matching events with `fetchall()`. Summary dimension lists can grow with member/device cardinality even within a short window. See [analytics/service.py:153](/home/gao20/projects/costguard/costguard-core/costguard_split/analytics/service.py:153) and [analytics/timeseries.py:88](/home/gao20/projects/costguard/costguard-core/costguard_split/analytics/timeseries.py:88). Require an explicit window policy and acknowledgment that pagination deferral does not bound query memory. Do not silently truncate aggregates or hashed documents.

3. **Rate limiting and caching may be deferred; require `Cache-Control: no-store` now.** Make the draft’s tentative position normative. Apply it to consumption success **and error** responses, including framework-generated validation errors. A header assigned only inside successful handlers will miss those responses. This is an HTTP transport policy, compatible with the prohibition on introducing a cache.

**B–C) Contradictions and required exact amendments**

The following replacement/addition text is my proposed approval condition.

**1. Classification and relationship to the precedent — amend.**

The opening incorrectly says “four existing P1D read layers” while naming three, and attributes the time-series read model to P1C-02. The read service is P1C-01; P1C-02 adds its HTTP adapter.

Replace draft lines 22–24 with:

> “If separately authorized for implementation, this gate permits HTTP consumption of existing analytics and visualization projections, the P1C-01 time-series read model, and the three P1D read layers: export, dashboard, and report. P1C-02 supplies the existing trend HTTP adapter.”

Replace the relationship bullets at lines 78–84 with:

> “The P1B-03 gate specified `/internal/visualization/*`; the implementation exposes `/api/v1/visualization/*`, including the trend route subsequently added by P1C-02. Preserve all implemented visualization routes and their contracts unchanged. Add `/api/v1/consumption/*` without aliases, replacement, or deprecation in this slice.”

The precedent explicitly deferred trend pending a time-series model: [P1B-03 gate:298](/home/gao20/projects/costguard/costguard-core/docs/gates/P1B_03_VISUALIZATION_API_GATE.md:298).

**2. Tenant isolation — amend; blocking correctness issue.**

“Same `_check_org` pattern” is insufficient: both existing guards bypass checks when `context is None`, and `create_app()` defaults to that state. See [visualization.py:24](/home/gao20/projects/costguard/costguard-core/costguard_split/api/visualization.py:24) and [app.py:44](/home/gao20/projects/costguard/costguard-core/costguard_split/api/app.py:44). Copying this behavior would contradict the draft’s mandatory authorization boundary and [context.py:4](/home/gao20/projects/costguard/costguard-core/costguard_split/api/context.py:4).

Replace the tenant requirements with:

> “Every consumption data endpoint requires an explicit `org_id` and a non-null, server-supplied `ServerContext`. Missing context or an `org_id` mismatch returns `404` with `{"detail":"not found"}` before calling any read service. Client query parameters, bodies, and headers MUST NOT create or select the authoritative context. This change applies only to consumption routes.”

Replace “unknown org / foreign org” in the error contract with:

> “Missing server context or requested organization differing from the context returns 404. A matching context organization with no matching usage returns the existing empty read-model representation. No organization-existence database lookup is introduced.”

The current read services do not validate organization existence; they filter usage rows. Equality with a context is not an existence check.

**3. Dashboard filtering — amend; blocking semantic issue.**

The draft promises summary inputs plus granularity, but `dashboard_projection()` applies filters only to summary-derived sections; trend remains organization-wide. Its metadata nevertheless echoes the filters. See [dashboard/service.py:47](/home/gao20/projects/costguard/costguard-core/costguard_split/dashboard/service.py:47) and [dashboard/service.py:62](/home/gao20/projects/costguard/costguard-core/costguard_split/dashboard/service.py:62).

For this slice, replace dashboard inputs with:

> “Required query parameters: `org_id`, `start`, `end`, and `granularity=day|hour`. Dashboard filters are not supported in this slice. Requests containing `provider`, `model`, `member_id`, or `device_id` return 422; they MUST NOT be silently ignored. The adapter calls `dashboard_projection()` without filters. Filtered dashboard trends require a separately authorized read-model change.”

This avoids modifying the forbidden analytics/dashboard layers or exposing a misleading composite.

**4. Response contract — amend.**

The DTO references are useful but incomplete:

- Dashboard serialization contains top-level `provider_distribution`, `model_distribution`, and `extra`; there is no `distributions` property. See [dashboard/dto.py:41](/home/gao20/projects/costguard/costguard-core/costguard_split/dashboard/dto.py:41).
- Distribution export also includes a visualization `summary`, beyond the two distribution lists. See [export/service.py:153](/home/gao20/projects/costguard/costguard-core/costguard_split/export/service.py:153).
- Report cost nulls become empty Markdown cells, not JSON nulls inside the body. See [report/service.py:57](/home/gao20/projects/costguard/costguard-core/costguard_split/report/service.py:57).

Add:

> “All successful consumption responses are JSON. `/distributions` returns exactly `provider_distribution` and `model_distribution`, each containing serialized `DistributionPoint` objects with `dimension`, `key`, `events`, and `tokens`. `/dashboard` returns `meta`, `totals`, `provider_distribution`, `model_distribution`, `trend`, and `extra`. Export endpoints preserve the complete existing `ExportDocument.to_dict()` output, including the distribution payload’s `summary`. Report endpoints preserve `ReportDocument.to_dict()`, with Markdown in the `body` string; no file download or HTML rendering is added.”

Add to versioning:

> “The v1 stability commitment applies only to `/api/v1/consumption/*`. It covers field names, types, nullability, query semantics, ordering semantics, and documented errors. Internal DTO changes do not automatically authorize wire-contract changes. Preserve existing document schema versions, baseline metadata, hash algorithms, and hash inputs. Success-shape requirements do not replace documented error bodies.”

This avoids retroactively granting stability to every existing `/api/v1` endpoint. The prior gate expressly excluded a backward-compatibility guarantee: [P1B-03 gate:248](/home/gao20/projects/costguard/costguard-core/docs/gates/P1B_03_VISUALIZATION_API_GATE.md:248).

**5. Time validation and pagination — amend.**

K12 has no expected behavior. Services use string comparisons for the window; ingestion normalizes timestamps to UTC. See [analytics/service.py:125](/home/gao20/projects/costguard/costguard-core/costguard_split/analytics/service.py:125) and [ingest/service.py:56](/home/gao20/projects/costguard/costguard-core/costguard_split/ingest/service.py:56).

Add this explicit proposed policy:

> “`start` and `end` must be timezone-aware ISO-8601 timestamps. Normalize them to the ingestion UTC serialization before calling services. The window is `[start,end)` and must satisfy `start < end` and a maximum duration of 31 days. Malformed, timezone-naive, reversed, empty, or oversized windows return 400. Missing required parameters return 422. Validate granularity before service invocation, including for empty datasets.”

Replace the pagination exclusion with:

> “Pagination is deferred for the initial internal surface. The window limit does not bound event or dimension cardinality, and existing services materialize matching events. Responses are complete, without silent truncation. Public or larger-scale operational exposure requires a separate resource-control review.”

The 31-day limit is a **proposed gate decision**, not an existing code constraint.

**6. Health, caching, and file boundary — amend.**

The unscoped health endpoint conflicts with “Every endpoint MUST require org_id.” The application already has `/healthz` at [app.py:57](/home/gao20/projects/costguard/costguard-core/costguard_split/api/app.py:57).

Replace the proposed consumption health endpoint with:

> “No additional health endpoint is introduced. Existing `/healthz` remains unchanged.”

Replace the tentative caching policy with:

> “Every response under `/api/v1/consumption/` MUST carry `Cache-Control: no-store`, including validation and error responses. Rate limiting, application caching, ETags, and conditional responses remain deferred.”

Clarify the allowed `app.py` modification:

> “Allow importing and invoking the consumption adapter’s registration function before `include_router()`. Any namespace-scoped response policy is implemented in `consumption.py` and installed by that function; it must not change existing routes’ behavior.”

**7. Required tests and authorization — amend.**

Repeated calls being equal do not prove schema compatibility. Row counts remaining stable do not detect updates. Add:

> “Tests must verify explicit baseline response keys/types/nullability; service-output parity; unchanged export/report hashes; missing-context rejection before service calls; organization isolation across every data endpoint; rejected dashboard filters; defined time-validation outcomes; invalid granularity with empty and populated data; and no-store headers on success and error responses. Mutation checks must detect changed row contents as well as row counts. Preserve and run both visualization API and trend API regression suites. NULL preservation follows each existing representation, including empty Markdown cost cells.”

Add to authorization requirements:

> “Before coding authorization, identify the authoritative CostGuard `DECISIONS.md` and reconcile this gate with its applicable conventions, or explicitly record that no such document applies. Reviewer approval of the amended design does not itself authorize coding; implementation-plan, file-boundary, test-plan approval, and the stated user sign-off remain required.”

**D) Roadmap scope**

Versioning and a stable consumption contract are **within** scope: [roadmap:265](/home/gao20/projects/costguard/costguard-core/docs/spec/CostGuard_Split_ROADMAP_v0.1.md:265) explicitly calls for a “Stable external consumption interface” and a separate API gate.

Clarify “external” with:

> “External consumption means consumers outside the Python modules; this slice remains internally deployed. It does not authorize public internet availability or a SaaS service commitment.”

The actual scope risks are extending stability to the entire `/api/v1` namespace, replacing legacy routes, or adding filtered time-series aggregation to fulfill the dashboard promise. The amendments above exclude those expansions. Baseline, read-only objective, architecture boundary, authentication deferral, storage exclusions, and dependency exclusions are otherwise acceptable.

**Final verdict: AMEND-THEN-APPROVE — apply amendments 1–7 above; coding remains unauthorized until the amended gate’s prerequisites are satisfied.**
