"""Single-file HTML report — self-contained, offline, shareable.

- NO external assets: inline CSS only; zero <script>, zero http(s) URLs
  (verified by tests). Opens via file:// in any browser.
- Model/provider strings are user-influenced data => html.escape()d.
- Privacy footer states local-only processing explicitly.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone


def _bar(pct: float) -> str:
    width = max(0, min(100, round(pct)))
    return (f'<div class="bar"><div class="fill" style="width:{width}%"></div>'
            f"</div>")


def _rows(items: list[tuple[str, int, float]], label: str) -> str:
    if not items:
        return ""
    rows = []
    for name, tokens, pct in items:
        n = html.escape(str(name))
        rows.append(
            f"<tr><td class='name'>{n}</td>"
            f"<td class='num'>{tokens:,}</td>"
            f"<td class='pct'>{pct}%</td>"
            f"<td class='barcell'>{_bar(pct)}</td></tr>")
    head_label = label[:-1] if label.endswith("e") else label
    return (f"<h2>{label}</h2><table><thead><tr><th>{head_label}</th>"
            f"<th>Tokens</th><th>Share</th><th></th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>")


_CSS = """
body{font-family:-apple-system,'Segoe UI',Roboto,sans-serif;max-width:760px;
margin:2rem auto;padding:0 1rem;color:#1a1a2e;background:#fafafa}
h1{font-size:1.5rem;border-bottom:3px solid #4f6df5;padding-bottom:.4rem}
h2{font-size:1.05rem;margin:1.6rem 0 .5rem;color:#4f6df5}
.cards{display:flex;gap:1rem;flex-wrap:wrap;margin:1rem 0}
.card{background:#fff;border:1px solid #e5e7eb;border-radius:10px;
padding:.9rem 1.2rem;flex:1;min-width:150px}
.card .v{font-size:1.45rem;font-weight:700}
.card .k{font-size:.75rem;color:#6b7280;text-transform:uppercase;
letter-spacing:.05em}
table{width:100%;border-collapse:collapse;background:#fff;border:1px solid
#e5e7eb;border-radius:8px}
th,td{padding:.5rem .7rem;text-align:left;border-bottom:1px solid #eef0f3;
font-size:.9rem}
th{color:#6b7280;font-weight:600;font-size:.75rem;text-transform:uppercase}
.num{text-align:right;font-variant-numeric:tabular-nums}
.pct{width:3.5em;text-align:right;color:#4f6df5;font-weight:600}
.barcell{width:34%}
.bar{background:#eef0f3;border-radius:4px;height:8px;overflow:hidden}
.fill{background:linear-gradient(90deg,#4f6df5,#7c9bff);height:100%}
.note{background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;
padding:.7rem 1rem;font-size:.85rem;margin:1rem 0}
.priv{background:#ecfdf5;border:1px solid #a7f3d0;border-radius:8px;
padding:.7rem 1rem;font-size:.85rem;margin:1rem 0}
footer{margin-top:2rem;font-size:.75rem;color:#9ca3af;line-height:1.6}
"""


def render_html(report: dict, generated_at: str | None = None) -> str:
    """report dict (build_report output) -> standalone HTML document."""
    e = html.escape
    rep = report
    cost = rep.get("cost") or {}
    gen = generated_at or datetime.now(tz=timezone.utc).isoformat()

    cards = [f'<div class="card"><div class="v">'
             f"{rep.get('total_tokens', 0):,}</div>"
             f'<div class="k">Tokens</div></div>',
             f'<div class="card"><div class="v">'
             f"~${cost.get('total_estimate', 0.0):,.2f}</div>"
             f'<div class="k">Est. Cost</div></div>',
             f'<div class="card"><div class="v">'
             f"{rep.get('events', 0)}</div>"
             f'<div class="k">Events</div></div>']

    models = [(m["model"], m["tokens"], m["share_pct"])
              for m in rep.get("model_share", [])]
    sources = [(src, d["tokens"], d.get("share_pct", 0.0))
               for src, d in sorted(rep.get("by_source", {}).items(),
                                    key=lambda kv: -kv[1]["tokens"])]
    providers = [(p, d["tokens"], d.get("share_pct", 0.0))
                 for p, d in sorted(rep.get("by_provider", {}).items(),
                                    key=lambda kv: -kv[1]["tokens"])]

    unpriced = cost.get("unpriced_models") or []
    unknown = cost.get("unknown_events", 0)
    cost_note = ""
    if unknown or unpriced:
        models_txt = e(", ".join(unpriced)) if unpriced else ""
        cost_note = (f'<div class="note"><b>Unknown cost:</b> {unknown} '
                     f"event(s) involve models without a local price"
                     + (f" ({models_txt})" if models_txt else "")
                     + ". They are shown as <b>unknown</b> — never counted "
                       "as $0.</div>")

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CostGuard — AI Usage Report {e(rep.get('date', ''))}</title>
<style>{_CSS}</style></head><body>
<h1>AI Usage Report <span style="color:#9ca3af;font-size:1rem">{
    e(rep.get('date', ''))}</span></h1>
<div class="cards">{''.join(cards)}</div>
{_rows(sources, "By Source")}
{_rows(providers, "By Provider")}
{_rows(models, "Model Share")}
<h2>Cost Estimate</h2>
<div class="cards">
<div class="card"><div class="v">~${cost.get('local_estimate', 0.0):,.2f}</div>
<div class="k">Local price table</div></div>
<div class="card"><div class="v">~${cost.get('source_estimate', 0.0):,.2f}</div>
<div class="k">Reported by tools</div></div>
</div>
{cost_note}
<div class="priv"><b>Privacy:</b> all data on this page was collected and
processed <b>locally</b> on this device. CostGuard never reads your prompts,
responses, or code, and never uploads anything.</div>
<footer>Generated {e(gen)} &middot; CostGuard Free (local price table
{e(str(cost.get('price_table_version', '?')))}); all cost figures are
approximate estimates. Token counts for tools that only report cumulative
usage are approximate by nature.<br>
This file contains only aggregated metadata — no prompts, responses, code,
file paths, or secrets.</footer>
</body></html>"""
