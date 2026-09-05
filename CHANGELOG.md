# CostGuard Agent — Changelog

## 0.2.0-beta (2026-09-05)

First public-ready release: CostGuard Free — local-first AI usage
intelligence. Install, scan, and see what your AI usage looks like.
No account, no cloud, no telemetry, zero network requests.

### Added
- Cost estimates (~) via a bundled offline price table
  (`price_table_version` stamped on every report).
- Model alias normalization (`k3` → `kimi-k3`,
  `custom:gpt-5.5/gpt-5.5` → `gpt-5.5`, …) — unknown models are shown
  as **unknown**, never silently counted as $0.
- Provider dimension in reports (By Provider table + `providers[]` in
  the JSON contract).
- `costguard report --html` — single-file, self-contained offline HTML
  report (inline CSS only; no scripts, no external URLs).
- `costguard data --delete [--yes]` — remove all local CostGuard data.
- Bundled price table ships inside the wheel (`pricing.json`).

### Connectors
- Hermes Agent (per-call token breakdown, cost-status pass-through).
- Codex CLI (cumulative per-thread totals; approximate — marked as such).

### Privacy
- Reads only whitelisted metadata columns; prompts/responses/code/paths/
  secrets are excluded at the SQL level and guarded by automated tests.
- Zero network requests anywhere (verified by a networking-disabled test).
- All local data in `~/.costguard/` with 0600 permissions.

### Known limitations
- Cost figures are estimates from a community snapshot table; models
  without a price are reported as unknown.
- Tools that only report cumulative usage produce approximate daily
  attributions.
- Non-listed AI tools are skipped gracefully (more connectors planned).

### Upgrade notes
- 0.1.x local databases are read as-is; no migration required for
  reading. New columns are additive.
