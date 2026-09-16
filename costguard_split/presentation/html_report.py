"""Deterministic, inert HTML presentation; the caller owns all I/O."""
from __future__ import annotations

from html import escape

from costguard_split.report.dto import ReportDocument


def _text(value: str | None) -> str:
    return 'Not specified' if value is None else escape(value, quote=True)


def render_report_html(document: ReportDocument) -> str:
    """Render existing values only; the body hash does not authenticate the HTML."""
    meta = document.meta
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CostGuard usage report</title>
<style>
body {{ margin: 0; background: #f4f6f8; color: #17212b; font-family: system-ui, sans-serif; line-height: 1.5; }}
main {{ max-width: 64rem; margin: auto; padding: 2rem; }}
section {{ background: white; border: 1px solid #d6dde4; padding: 1.25rem; margin: 1rem 0; border-radius: .4rem; }}
dt {{ font-weight: bold; margin-top: .65rem; }}
dd {{ margin-left: 0; overflow-wrap: anywhere; white-space: pre-wrap; }}
pre {{ white-space: pre-wrap; overflow-wrap: anywhere; font-family: ui-monospace, monospace; }}
@media print {{ body {{ background: white; }} main {{ padding: 0; }} }}
</style>
</head>
<body>
<main>
<h1>CostGuard usage report</h1>
<section aria-labelledby="metadata-heading">
<h2 id="metadata-heading">Report metadata</h2>
<dl>
<dt>Schema version</dt><dd>{_text(meta.schema_version)}</dd>
<dt>Baseline</dt><dd>{_text(meta.baseline)}</dd>
<dt>Window start</dt><dd>{_text(meta.window_start)}</dd>
<dt>Window end</dt><dd>{_text(meta.window_end)}</dd>
<dt>Granularity</dt><dd>{_text(meta.granularity)}</dd>
<dt>Provider</dt><dd>{_text(meta.provider)}</dd>
<dt>Model</dt><dd>{_text(meta.model)}</dd>
<dt>Member</dt><dd>{_text(meta.member_id)}</dd>
<dt>Device</dt><dd>{_text(meta.device_id)}</dd>
<dt>Report body content hash</dt><dd>{_text(document.content_hash)}</dd>
</dl>
<p>The supplied hash describes the report body; it does not cover this HTML.</p>
</section>
<section aria-labelledby="content-heading">
<h2 id="content-heading">Report content</h2>
<pre><code>{_text(document.body)}</code></pre>
</section>
</main>
</body>
</html>
'''
