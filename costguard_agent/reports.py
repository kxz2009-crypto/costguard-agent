"""Report engine — reads ONLY usage_fact (never connectors, never sources).

Cost handling (honest accounting):
- estimated_cost is shown ONLY as pass-through with its status; events
  with cost_status='unknown' contribute tokens but their cost stays in
  the 'unknown' bucket — never merged into the priced total.
- No pricing_registry yet (planned phase): collector never prices.
"""

from __future__ import annotations

from collections import defaultdict

from . import database
from .pricing import PriceTable, cost_usd
from .usage_event import SCHEMA_VERSION, UNKNOWN, TOKEN_FIELDS


def _rows_for_date(db, day: str):
    return db.execute(
        "SELECT source, provider, model, input_tokens, output_tokens,"
        " all_tokens, estimated_cost, cost_status, event_date"
        " FROM usage_fact WHERE event_date=?",
        (day,)).fetchall()


def _bucket(rows, key_idx):
    # token column moved to idx 5 when input/output split was added
    agg = defaultdict(lambda: {"tokens": 0, "events": 0})
    for r in rows:
        agg[r[key_idx]]["tokens"] += r[5]
        agg[r[key_idx]]["events"] += 1
    return agg


def build_report(day: str | None = None) -> dict:
    db = database.connect()
    try:
        if day is None:
            day = db.execute(
                "SELECT MAX(event_date) FROM usage_fact"
                " WHERE event_date != 'unknown'").fetchone()[0]
        rows = _rows_for_date(db, day) if day else []
        report = {"schema_version": SCHEMA_VERSION,
                  "date": day or "unknown", "total_tokens": 0,
                  "by_source": {}, "model_share": [], "cost": {}}
        if not rows:
            return report

        total = sum(r[5] for r in rows)
        report["total_tokens"] = total
        report["events"] = len(rows)

        # provider breakdown (provider now a first-class report dimension)
        for prov, agg in _bucket(rows, 1).items():
            report.setdefault("by_provider", {})[prov] = {
                "tokens": agg["tokens"],
                "events": agg["events"],
                "share_pct": round(100.0 * agg["tokens"] / total, 1) if total else 0.0,
            }

        # per-source breakdown
        for src, agg in _bucket(rows, 0).items():
            report["by_source"][src] = {
                "tokens": agg["tokens"],
                "events": agg["events"],
                "share_pct": round(100.0 * agg["tokens"] / total, 1) if total else 0.0,
            }

        # model share (token-desc), top 6 + Others per REPORT-SPEC §6
        models = _bucket(rows, 2)
        ranked = sorted(models.items(), key=lambda kv: -kv[1]["tokens"])
        top, others_tok = ranked[:6], 0
        for name, agg in ranked[6:]:
            others_tok += agg["tokens"]
        share = []
        for name, agg in top:
            share.append({"model": name,
                          "tokens": agg["tokens"],
                          "share_pct": round(100.0 * agg["tokens"] / total, 1)})
        if others_tok:
            share.append({"model": "others", "tokens": others_tok,
                          "share_pct": round(100.0 * others_tok / total, 1)})
        report["model_share"] = share

        # cost section: three disjoint buckets, never mixed
        #   local_estimate : priced via bundled price table (shows as ~)
        #   source_estimate: cost_status='estimated' pass-through from source
        #   unknown        : no reliable price — rendered "unknown", NEVER $0
        pt = PriceTable.load_builtin()
        local_est = 0.0
        source_est = 0.0
        unpriced_models: set[str] = set()
        unknown_events = 0
        for r in rows:
            _, _, model, itok, otok, _, pass_cost, status, _ = r
            if status == "estimated":
                source_est += pass_cost
                continue
            unknown_events += 1
            price = pt.lookup(model)
            if price is None:
                unpriced_models.add(model)
                continue
            local_est += cost_usd(price, itok or 0, otok or 0)
        report["cost"] = {
            "local_estimate": round(local_est, 8),
            "source_estimate": round(source_est, 8),
            "total_estimate": round(local_est + source_est, 8),
            "unknown_events": unknown_events,
            "unpriced_models": sorted(unpriced_models),
            "price_table_version": pt.table_version,
        }
        return report
    finally:
        db.close()


def to_machine_report(rep: dict) -> dict:
    """Stable JSON shape for `report --json` / SaaS ingestion.

    v1.1 additions (additive, non-breaking): providers[], cost section
    reworked to local_estimate/source_estimate/total_estimate +
    unknown_events + unpriced_models + price_table_version.
    Field removals/renames require SCHEMA_VERSION bump.
    """
    return {
        "schema_version": rep.get("schema_version", SCHEMA_VERSION),
        "date": rep["date"],
        "total_tokens": rep["total_tokens"],
        "models": [
            {"model": m["model"], "tokens": m["tokens"],
             "share_pct": m["share_pct"]}
            for m in rep.get("model_share", [])
        ],
        "sources": [
            {"source": src, "tokens": d["tokens"],
             "events": d["events"], "share_pct": d["share_pct"]}
            for src, d in sorted(rep.get("by_source", {}).items(),
                                 key=lambda kv: -kv[1]["tokens"])
        ],
        "providers": [
            {"provider": p, "tokens": d["tokens"],
             "events": d["events"], "share_pct": d["share_pct"]}
            for p, d in sorted(rep.get("by_provider", {}).items(),
                               key=lambda kv: -kv[1]["tokens"])
        ],
        "cost": {
            "local_estimate": rep["cost"].get("local_estimate", 0.0),
            "source_estimate": rep["cost"].get("source_estimate", 0.0),
            "total_estimate": rep["cost"].get("total_estimate", 0.0),
            "unknown_events": rep["cost"].get("unknown_events", 0),
            "unpriced_models": rep["cost"].get("unpriced_models", []),
            "price_table_version": rep["cost"].get("price_table_version", ""),
        },
    }


def format_report(rep: dict) -> str:
    L = []
    L.append("CostGuard Local — AI Usage Report")
    L.append(f"Date: {rep['date']}")
    L.append("")
    L.append("Today Usage")
    L.append(f"  Token Total: {rep['total_tokens']:,}")
    if rep.get("events"):
        L.append(f"  Events:      {rep['events']}")
    if rep["by_source"]:
        L.append("")
        L.append("By Source")
        for src, d in sorted(rep["by_source"].items(),
                             key=lambda kv: -kv[1]["tokens"]):
            L.append(f"  {src:8s} {d['tokens']:>13,}  ({d['share_pct']}%)")
    if rep.get("by_provider"):
        L.append("")
        L.append("By Provider")
        for p, d in sorted(rep["by_provider"].items(),
                           key=lambda kv: -kv[1]["tokens"]):
            L.append(f"  {p:14s} {d['tokens']:>13,}  ({d['share_pct']}%)")
    if rep["model_share"]:
        L.append("")
        L.append("Model Share")
        for m in rep["model_share"]:
            L.append(f"  {m['model']:22s} {m['tokens']:>13,}  ({m['share_pct']}%)")
    c = rep.get("cost") or {}
    if c:
        L.append("")
        L.append("Cost Estimate (approximate, local price table "
                 f"{c.get('price_table_version', '?')})")
        L.append(f"  ~ est. total:   ${c.get('total_estimate', 0.0):.2f}")
        L.append(f"    local est:   ${c.get('local_estimate', 0.0):.2f}"
                 f"  (bundled price table)")
        L.append(f"    source est:  ${c.get('source_estimate', 0.0):.2f}"
                 f"  (reported by the tool itself)")
        unk = c.get("unknown_events", 0)
        unpriced = c.get("unpriced_models", [])
        if unk or unpriced:
            L.append(f"  unknown cost:   {unk} events"
                     + (f" (models without a local price: "
                        f"{', '.join(unpriced)})" if unpriced else ""))
            L.append("  (shown as unknown, never counted as $0)")
    return "\n".join(L)
