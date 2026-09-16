# Hermes incremental collection — local acceptance scope

The owner requested continued work after the real-metadata snapshot test and
authorized routine reversible local work. This adds native cumulative Hermes
collection, durable incremental checkpoint/outbox state and focused tests.
It does not authorize profile/model changes, background jobs, commits or deploy.

## Boundary

New package costguard_split.collection exposes HermesIncremental and the command
`python -m costguard_split.collection.hermes --source-db SOURCE --state-dir STATE
--device-uid UID`. Run from the installed package or repository. STATE must be
outside the source directory and dedicated to this collector. It is private local
state, not a location for source data or public artifacts. Existing package
metadata already includes costguard_split*; no new dependencies are required.

This cumulative coordinator intentionally is not a stateless BaseConnector:
Claude/Codex registry contracts remain unchanged. Its durable outbox holds only
UsageEventClaim data. It never determines organization/member/cost authority.

## Data and timing contract

Read only session/model/provider, cumulative counters, first/last timestamps.
Group by session/model/provider so billing mode, billing URL and task fields
never have to be selected. This is a per-group cumulative observation, not one
API call per event; request_count carries the native call-count delta.

Session identity is HMAC-pseudonymized with a random persisted local salt.
Models/provider names and usage counters remain metadata, not anonymous data.
No credential/config/prompt/message source is read or exported. Counter fields
are preserved as supplied, with no inference about overlapping cached/reasoning
classes or billing. Public-pricing accuracy is not part of this acceptance.

The first scan defaults to baseline-only. Explicit --include-history imports
initial cumulative history; it cannot backfill a baseline already accepted.
New groups after initialization are included in full. Deltas use previous
last_seen through current last_seen as their observation interval; they cannot
reconstruct exact call timestamps or exact member allocation when an interval
crosses a reassignment. Keep pricing disabled pending semantic validation.

## Durability and failure handling

One SQLite BEGIN IMMEDIATE serializes source snapshot and state/outbox changes.
An update cannot advance its checkpoint without persisting its pending claim.
Event IDs use the private stream digest and monotonic revision. Repeated scans
emit no delta; source counter/time/first_seen regression aborts the scan and
retains prior state rather than guessing a reset. An empty unobserved zero row
is counted separately. Missing source groups are retained in checkpoints.

The state is bound to source path/inode/device; source replacement or device
changes require explicit investigation and a separate migration plan. Do not
silently delete/recreate state to recover: that can lose queued data or repeat
historical imports. Back up the entire checkpoint DB, including outbox and salt.
The checkpoint DB is 0600 and its dedicated directory 0700. Do not copy it to a
public report location. Unknown checkpoint schemas fail closed.

`deliver(send)` accepts a caller-owned transport callback returning an HTTP-like
response. Only matching 200/201 receipts acknowledge claims. Exceptions/failure
leave them pending; retries can send more than once, and server source-event
idempotency prevents duplicate storage. Parallel senders may both transmit the
same claim; this is at-least-once delivery, not exactly-once network execution.
No automatic network transport, credential loading, daemon or scheduler is added.

## Validation requirements

First/new/empty sources, incremental counters, repeated scans, concurrent scans,
reset/stale-source rollback, private identity, state path guards, source file
replacement, lost acknowledgements, invalid receipts, server deduplication and
sum preservation. Real source trial must use only metadata and baseline mode;
no real claims may be uploaded as part of automatic acceptance.

## Review-driven hardening

Checkpoint schema is version 2. Pre-review version 1 must not be reused because
provider identity handling changed; unknown versions are rejected without reset.
SourceRegression now persists a halted flag after rolling back all scan changes.
It survives restarts and prevents new delivery attempts. Explicit
resume_after_investigation() or --resume-after-investigation only clears the
halt; it never adjusts checkpoints and an unresolved regression halts again.

Each operation validates directory/file identity, regular-file and owner/link
properties. Private inode descriptors are pinned for the collector lifetime;
POSIX flock serializes cooperating access through SQL close. Use close() or the
context-manager interface for deterministic descriptor cleanup. This collector
is POSIX-only and does not claim protection against root or hostile code running
under the same operating-system identity with access to its private state.
