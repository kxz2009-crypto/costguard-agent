# Cloud debug transaction follow-up — 2026-09-13

Owner requested continued work until cloud debugging is possible and supplied
costguardsplit.nuxnow.com. Cloud deployment itself remains unapproved pending
server access details. No commit/push/merge/deploy was performed.

Bridge job 4a7507c0b8ef40ffa9b3225c49538ef3 completed NEED_FIX:
F1 concurrent handlers share transaction ownership; F2 failed audited writes
remain pending and can be committed by later requests.

The API factory now installs RequestScope middleware: complete HTTP requests,
including async batches, are serialized on one connection; unfinished
transactions are rolled back in finally before another request enters.
Existing successful service commit points and partial-success batch contracts
are unchanged. Direct service callers continue to own transaction discipline.
This is single-process test operation, not a scalable per-request DB redesign.

Regression cases reproduce failure leakage and concurrent entry before the fix.
After the fix: member create/update audit failure rollback, device registration
audit failure rollback, and deterministic concurrent exclusion pass.
Full source suite: 343 passed / 2 Git-check skips / 2 existing warnings.
Legacy contracts: 18 passed / 2 live-source skips / 0 failed.
Rebuilt wheel and sdist wheel pass installed rendering checks.

The cloud-debug bundle is outside product source in the task outputs. It uses
one backend instance, dedicated synthetic database volume, edge authentication,
TLS and private backend networking. Its runtime acceptance and independent
re-review are recorded in the task outputs, not implied by this note.

Second bridge review 3520a0245b4b475b868bd107e5e27c24 completed PASS, no findings.
This is a static review, not independent execution of the claimed full tests.
Local container verification passed 15 checks: private-CA TLS, authentication,
origin rejection, tenant guard, registration, ingestion/deduplication, report
JSON to installed HTML, concurrent writes, restart persistence, non-root user
and unpublished backend port. Cloud DNS/ACME/firewall verification remains
pending along with target-server access and explicit deployment authorization.
