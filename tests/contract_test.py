"""Connector contract tests (P0-CORE-HARDENING §5).

Run: python -m tests.contract_test
Verifies for EVERY registered connector:
  T1  SQL safety   — declared select_sql contains no content columns
                     (static check; source DBs are NEVER opened)
  T2  read-only    — sources opened via mode=ro URI only
  T3  schema       — every produced UsageEvent satisfies the stable
                     contract (required fields, token types, cost_status)
Plus pipeline-level checks on the machine report / export payload.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from costguard_agent.connector_base import verify_sql_safety  # noqa: E402
from costguard_agent.connectors.hermes import HermesConnector  # noqa: E402
from costguard_agent.connectors.codex import CodexConnector  # noqa: E402
from costguard_agent.usage_event import (  # noqa: E402
    CONTRACT_FIELDS, REQUIRED_FIELDS, SCHEMA_VERSION, TOKEN_FIELDS, UsageEvent)

CONNECTORS = (HermesConnector, CodexConnector)

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((PASS if ok else FAIL, name, detail))


def test_t1_sql_static() -> None:
    for cls in CONNECTORS:
        problems = verify_sql_safety(cls)
        check(f"T1 {cls.id}: select_sql content-free", not problems,
              "; ".join(problems))
        check(f"T1 {cls.id}: select_sql declared", bool(cls.select_sql))


def test_t1_negative_guard() -> None:
    """The guard must actually reject content SQL (guard-the-guard)."""
    bad = "SELECT prompt, response FROM threads"
    problems = verify_sql_safety(type("Bad", (), {
        "id": "bad", "select_sql": (bad,)}))
    check("T1 guard rejects content SQL", bool(problems), str(problems))


def test_t2_readonly_uri() -> None:
    import inspect
    from costguard_agent import connector_base
    src = inspect.getsource(connector_base.ro_connect)
    check("T2 ro_connect uses mode=ro", "mode=ro" in src)
    for cls in CONNECTORS:
        import costguard_agent.connectors.hermes as hm
        import costguard_agent.connectors.codex as cx
        mod = hm if cls is HermesConnector else cx
        msrc = inspect.getsource(mod)
        check(f"T2 {cls.id}: uses ro_connect", "ro_connect(" in msrc)
        check(f"T2 {cls.id}: no connect( without mode=ro helper",
              "sqlite3.connect(" not in msrc)


def test_t3_event_contract() -> None:
    for cls in CONNECTORS:
        conn = cls()
        if not conn.discover()["installed"]:
            results.append(("SKIP", f"T3 {cls.id}: source not installed", ""))
            continue
        events = conn.scan()
        check(f"T3 {cls.id}: produced events", len(events) > 0,
              f"{len(events)} events")
        bad: list[str] = []
        for ev in events:
            bad.extend(f"{cls.id}: {p}" for p in ev.validate())
            # contract projection must contain exactly CONTRACT_FIELDS
            if set(ev.to_contract().keys()) != set(CONTRACT_FIELDS):
                bad.append(f"{cls.id}: to_contract keys drifted")
        check(f"T3 {cls.id}: all events satisfy contract", not bad,
              "; ".join(bad[:5]))


def test_t3_machine_report_shape() -> None:
    from costguard_agent.reports import build_report, to_machine_report
    rep = to_machine_report(build_report())
    expected_top = {"schema_version", "date", "total_tokens",
                    "models", "sources", "providers", "cost"}
    check("T3 report --json top-level keys", set(rep) == expected_top,
          str(set(rep) ^ expected_top))
    check("T3 report --json schema_version pinned",
          rep["schema_version"] == SCHEMA_VERSION)
    for m in rep["models"]:
        check("T3 model entry keys", set(m) == {"model", "tokens", "share_pct"})
        break
    for s in rep["sources"]:
        check("T3 source entry keys",
              set(s) == {"source", "tokens", "events", "share_pct"})
        break


def test_t3_export_payload_privacy() -> None:
    from costguard_agent import export as export_mod
    payload = export_mod.build_export_payload()
    try:
        export_mod.assert_no_forbidden_payload(payload)
        check("T3 export payload has no forbidden keys", True)
    except PermissionError as exc:
        check("T3 export payload has no forbidden keys", False, str(exc))
    blob = str(payload).lower()
    leaked = [w for w in ("prompt", "response", "api_key", "session_ref",
                          "first_user_message", "preview")
              if f'"{w}"' in blob]
    check("T3 export payload strings clean", not leaked, str(leaked))
    # privacy: no per-event/session granularity — day+model aggregation only
    sample = next(iter(payload["usage"].values()))
    check("T3 export granularity is day/model",
          set(sample) == {"tokens", "events", "cost", "models"})


def test_t3_synthetic_event_validation() -> None:
    ev = UsageEvent(provider="p", model="m", input_tokens=-1)
    problems = ev.validate()
    check("T3 validate() catches bad tokens", any("input_tokens" in p
                                                  for p in problems))
    ev2 = UsageEvent(provider="", model="m", timestamp="")
    problems2 = ev2.validate()
    check("T3 validate() catches missing required",
          any("provider" in p for p in problems2)
          and any("timestamp" in p for p in problems2))


def main() -> int:
    test_t1_sql_static()
    test_t1_negative_guard()
    test_t2_readonly_uri()
    test_t3_event_contract()
    test_t3_machine_report_shape()
    test_t3_export_payload_privacy()
    test_t3_synthetic_event_validation()

    failed = [r for r in results if r[0] == FAIL]
    skipped = [r for r in results if r[0] == "SKIP"]
    print("CONNECTOR CONTRACT TEST")
    for status, name, detail in results:
        line = f"  [{status}] {name}"
        if detail:
            line += f"  -- {detail}"
        print(line)
    print(f"\n{len(results)} checks: {len(results)-len(failed)-len(skipped)} passed,"
          f" {len(failed)} failed, {len(skipped)} skipped")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
