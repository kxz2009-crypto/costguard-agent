# P1D-04 Freeze Record

**Freeze point:** `34586686cf2080d3a38600f91e33861877c97e42` = `v0.8.0-p1d04-final` (annotated tag, local)
**Old legacy tag:** `v0.8.0-p1d04` → `c400e4b` — **untouched** (feature-tag, still the first-green baseline)
**Status:** CODE FROZEN (local). NOT pushed. Owner-pending release/approval record.

## Authority
Freeze executed per user's explicit instruction (verbatim):
> 先跑回滚演练，过了再正式冻结。

Sequence: round-3 green (already done) → rollback drill → freeze. Rollback drill passed, so freeze proceeds.

## Gate verdict summary (P1D_04_OPEN_CONSUMPTION_API_GATE.md)
- P1D-04 gate: **GREEN / GO / FROZEN** (round-3).
- K1–K22: **22 PASS, 0 FAIL** (K17 38→PASS).
- Round-3 full regression: `315 passed, 0 failed`.
- Isolated: trend 10p, consumption 26p, sequence-reversal 36p.
- Independent contract: `18 passed, 0 failed, 2 skipped` (connector not installed).
- Clean-DB TCP E2E: `17/17 PASS`.

## Rollback drill (the last hard blocker) — GO 27/27
Baseline = `v0.7.0-p1d03` = `d161f8c27f5d2df61e3161fd188ff8045a061830` (pre-P1D-04, no consumption, no org bootstrap).
Candidate = HEAD `3458668` (P1D-04 consumption API + org bootstrap).
Method: isolated `git worktree` for baseline (prod worktree + HEAD + legacy tag untouched), baseline served a **copy** of the candidate DB.

| # | Check | Result |
|---|-------|--------|
| 1 | baseline server starts & serves | PASS |
| 2 | health OK (root path, 200 ok) | PASS |
| 3–12 | 10 legacy routes present (404→NOT one) | PASS |
| 13–18 | 6 consumption routes absent (404) | PASS |
| 19 | org row retained (org-e2e) | PASS |
| 20 | data rows intact (usage/members/devices/assignments/audit/schema) | PASS |
| 21 | candidate DB byte-identical sha256 (a7a62401…) + reserved counts unchanged | PASS |
| 22 | prod HEAD unchanged, legacy v0.8.0-p1d04 untouched | PASS |
| 23 | worktree removed (candidate restored) | PASS |

Evidence: `/tmp/rollback-drill/rollback-drill-evidence.json`, `/tmp/costguard-e2e/round3/rollback-drill-summary.log`.

## Red lines honored
- Freeze = local annotated tag + record commit. **No push.** No new remote state.
- Legacy tag `v0.8.0-p1d04` (c400e4b) never moved.
- 51 historical evidence files + round-3 evidence bytes unchanged (drill touched only a copied DB).
- Prod worktree, HEAD, and remote all unchanged except the new local tag object.

## Owner-pending (explicitly NOT covered by this green/freeze)
1. Release/approval record (待批发布) — not yet aligned; this is owner sign-off, not a test result.
2. P1E scope — not defined, not implemented, not exposed; this green does not authorize it.

## Non-frozen note
`tests/e2e_p1d04_freeze_check.py` 2 skipped (connector not installed) — environment fact, not a gate failure.
