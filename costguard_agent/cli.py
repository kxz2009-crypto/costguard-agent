#!/usr/bin/env python3
"""costguard CLI — scan / report / connectors / export.

MVP commands (ROADMAP §13 First Milestone) + hardening additions:
  costguard scan              discover + collect + store (read-only on sources)
  costguard report            Today Usage / Model Share / Token Total / Cost
  costguard report --json     machine-readable contract output (SaaS-ready)
  costguard connectors        per-connector health
  costguard export            aggregated_usage.json (sync-prep; NO upload)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .connectors import Connector
from .connectors.hermes import HermesConnector
from .connectors.codex import CodexConnector
from . import database, export as export_mod, sync as sync_mod, device
from .reports import build_report, format_report, to_machine_report
from .html_report import render_html

CONNECTORS: list[type[Connector]] = [HermesConnector, CodexConnector]

# Upcoming connectors surfaced in first-run guidance (NOT scanned yet).
COMING_SOON = ("Claude Code",)

# Declarative summary used by scan/report empty states and --help epilog.
# Paths mirror each connector's allowed_paths so users can verify detection.
SUPPORTED = (
    ("Hermes", "~/.hermes/state.db"),
    ("Codex", "~/.codex/sqlite/state_5.sqlite"),
)


def _supported_block(prefix: str = "") -> str:
    """Human guidance shown when a scan/report finds no usage data."""
    lines = [
        f"{prefix}No AI usage data found.",
        "",
        f"{prefix}Supported connectors:",
    ]
    lines += [f"{prefix}  - {name:<12} ({path})" for name, path in SUPPORTED]
    lines += [f"{prefix}  - {name} (coming soon)" for name in COMING_SOON]
    lines += [
        "",
        f"{prefix}Next step: install and run a supported tool once,"
        f" then run: costguard scan",
    ]
    return "\n".join(lines)


def cmd_scan(_args) -> int:
    total_new = total_seen = 0
    print("CostGuard scan")
    for cls in CONNECTORS:
        conn = cls()
        d = conn.discover()
        if not d["installed"]:
            print(f"  {conn.id:8s} not found (skipped)")
            continue
        h = conn.health_check()
        if h["status"] != "connected":
            print(f"  {conn.id:8s} unavailable: {h.get('reason')}")
            continue
        events = conn.scan()
        new, seen = database.store(events)
        total_new += new
        total_seen += seen
        print(f"  {conn.id:8s} ✓ {len(events)} events ({new} new)")
    print(f"\nStored {total_new} new events ({total_seen} scanned)"
          f" -> {database.DB_PATH}")
    if total_new == 0:
        print()
        print(_supported_block())
    return 0


def cmd_report(args) -> int:
    rep = build_report(day=args.date)
    if getattr(args, "html", False):
        out = export_mod.EXPORT_DIR / "report.html"
        if args.out:
            out = Path(args.out).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_html(rep), encoding="utf-8")
        out.chmod(0o600)
        if rep["total_tokens"] == 0:
            print(f"No usage data for {rep['date']}.")
            print()
            print(_supported_block())
            print()
            print(f"(empty HTML report still written: {out})")
            return 1
        print(f"HTML report written: {out}")
        print("  (self-contained file; open it with any browser)")
        return 0
    if args.json:
        print(json.dumps(to_machine_report(rep), indent=2,
                         ensure_ascii=False))
        return 0 if rep["total_tokens"] else 1
    if rep["total_tokens"] == 0:
        print(f"No usage data for {rep['date']}.")
        print()
        print(_supported_block())
        return 1
    print(format_report(rep))
    return 0


def cmd_data(args) -> int:
    """Delete ALL local CostGuard data (~/.costguard). User owns their data."""
    import shutil
    root = database.CG_DIR
    if not root.exists():
        print("No local data found (nothing to delete).")
        return 0
    if not args.yes:
        print(f"This deletes EVERYTHING under {root}:")
        print("  - local database (usage history)")
        print("  - exports (report.html, aggregated_usage.json, DTO)")
        print("  - anonymous device id")
        print("Re-run with --yes to confirm.")
        return 1
    shutil.rmtree(root)
    print(f"Deleted {root}. All local CostGuard data removed.")
    return 0


def cmd_export(args) -> int:
    path = export_mod.export(path=args.out)
    payload = export_mod.build_export_payload()
    print(f"Exported {payload['days']} days,"
          f" {sum(d['tokens'] for d in payload['usage'].values()):,} tokens")
    print(f"  -> {path}")
    print("  (local file only; nothing was uploaded)")
    return 0


def cmd_connectors(_args) -> int:
    for cls in CONNECTORS:
        conn = cls()
        d = conn.discover()
        h = conn.health_check()
        print(f"{conn.id:8s} installed={d['installed']!s:5s}"
              f" status={h['status']:12s} events={h.get('events', '-')}")
    return 0


def cmd_sync(_args) -> int:
    st = sync_mod.status()
    did = device.get_or_create()
    print("CostGuard sync")
    print(f"  enabled:    {st['enabled']}  (default OFF; nothing uploads)")
    print(f"  transport:  {st['transport']}")
    print(f"  device_id:  {did}")
    print(f"  note:       {st['note']}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="costguard",
        description="CostGuard Local AI usage agent",
        epilog="Supported connectors:\n"
               "  - Hermes\n"
               "  - Codex\n"
               "  - Claude Code (coming soon)\n"
               "\n"
               "Privacy: runs locally, zero network, never reads prompts or"
               " responses.\n"
               "Get started: costguard scan",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan", help="discover and collect local AI tool usage")
    rp = sub.add_parser("report", help="print usage report")
    rp.add_argument("--date", default=None, help="YYYY-MM-DD (default: latest day)")
    rp.add_argument("--json", action="store_true",
                    help="machine-readable output (stable contract)")
    rp.add_argument("--html", action="store_true",
                    help="self-contained HTML report (single file, offline)")
    rp.add_argument("--out", default=None,
                    help="output path for --html (default ~/.costguard/exports/report.html)")
    sub.add_parser("connectors", help="connector health status")
    ep = sub.add_parser("export", help="export aggregated usage (local only)")
    ep.add_argument("--out", default=None,
                    help="output path (default ~/.costguard/exports/aggregated_usage.json)")
    sub.add_parser("sync", help="show sync status (default OFF; no upload)")
    dp = sub.add_parser("data", help="manage local data")
    dp.add_argument("--delete", dest="delete", action="store_true",
                    help="delete ALL local CostGuard data")
    dp.add_argument("--yes", action="store_true",
                    help="skip confirmation (required with --delete)")
    args = p.parse_args(argv)
    if args.cmd == "data":
        if not args.delete:
            print("usage: costguard data --delete [--yes]")
            return 2
        return cmd_data(args)
    return {"scan": cmd_scan, "report": cmd_report,
            "connectors": cmd_connectors, "export": cmd_export,
            "sync": cmd_sync}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
