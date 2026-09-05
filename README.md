# CostGuard Agent (Free)

**See your AI usage. Locally.**

CostGuard is a free, open, local-first tool that reads the usage metadata
your AI coding/CLI tools already write on your machine and turns it into a
clear report: tokens, models, providers, and an estimated cost — without
ever reading a single prompt, response, or line of code.

```
$ costguard scan
CostGuard scan
  hermes   ✓ 1405 events (1405 new)
  codex    ✓ 18 events (18 new)

$ costguard report
CostGuard Local — AI Usage Report
Date: 2026-09-04

Today Usage
  Token Total: 84,757,987
  Events:      60

By Source
  hermes      55,180,595  (65.1%)
  codex       29,577,392  (34.9%)

Model Share
  glm-5.3-flash             47,715,874  (56.3%)
  ...

Cost Estimate (approximate, local price table 2026-09-05)
  ~ est. total:   $295.77
```

## Install

Requires Python 3.10+.

```bash
pipx install costguard-agent     # recommended
# or: pip install costguard-agent
```

## 30-second quick start

```bash
costguard scan      # read local AI tools (read-only; nothing is sent)
costguard report    # terminal report
costguard report --html   # self-contained HTML file you can open/share
costguard report --json   # stable machine-readable output
```

Open `~/.costguard/exports/report.html` in any browser for a visual report.

## Supported AI tools

| Tool | Status | Notes |
|---|---|---|
| Hermes Agent | ✅ supported | per-call token breakdown |
| Codex CLI | ✅ supported | cumulative per-thread token totals (approximate split) |
| Claude Code | 🚧 planned | |
| Gemini CLI | 🚧 planned | |
| OpenCode | 🚧 planned | |

Not found tools are skipped gracefully — install CostGuard even if you use
only one of the above.

## Privacy (the short version)

- **Local only.** Everything is collected, processed, and stored on your
  machine (`~/.costguard/`). There is no account, no cloud, no telemetry,
  and CostGuard makes zero network requests.
- **Never collected:** prompts, responses, conversations, source code,
  documents, file paths, API keys, or any secrets. This is enforced in
  code (whitelisted metadata columns only) and covered by automated tests.
- **You own your data:** `costguard data --delete` removes everything.

Full model: see the Privacy and Transparency specification in the project docs.

## Accuracy notes (honest numbers)

- All cost figures are **estimates** (shown with `~`) computed from a
  bundled community price table (`price_table_version` appears in every
  report). Prices change; treat amounts as indicative.
- Models without a known price are shown as **unknown** — never silently
  counted as $0.
- Tools that only report cumulative token totals (e.g. Codex threads)
  produce approximate per-day attributions; reports mark these.

## Data & removal

- Data lives in `~/.costguard/` (database, exports, an anonymous random
  device id). File permissions: 0600.
- Delete everything: `costguard data --delete --yes`
  (or simply `rm -rf ~/.costguard`). Uninstalling the package does not
  touch your data.

## License

MIT — see [LICENSE](LICENSE).
