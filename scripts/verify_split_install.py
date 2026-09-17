#!/usr/bin/env python3
"""Verify a pip --target installation without falling back to checkout code.

Run with python -I scripts/verify_split_install.py INSTALL_DIR [--claims] [--server].
Use --server with an interpreter providing the split-server optional extras.
Use --claims with an interpreter providing the split optional extras.
"""
import argparse
import importlib
import importlib.metadata
import json
from pathlib import Path
import sys
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('install_dir', type=Path)
parser.add_argument('--claims', action='store_true')
parser.add_argument('--server', action='store_true')
a = parser.parse_args()
root = a.install_dir.resolve(strict=True)
sys.path.insert(0, str(root))
for name in ['costguard_agent', 'costguard_split', 'costguard_split.analytics.service',
             'costguard_split.analytics.timeseries', 'costguard_split.dashboard.service',
             'costguard_split.report.service', 'costguard_split.export.service']:
    module = importlib.import_module(name)
    assert Path(module.__file__).resolve().is_relative_to(root), (name, module.__file__)
pricing = json.loads((root / 'costguard_split/data/public_pricing.json').read_text())
assert pricing['version'] and pricing['models']
from costguard_split.report.dto import ReportDocument, ReportMeta
from costguard_split.presentation.html_report import render_report_html
sample = ReportDocument(ReportMeta('synthetic', 'baseline', 'start', 'end'), '<synthetic>', 'body-hash')
rendered = render_report_html(sample)
assert rendered.startswith('<!doctype html>')
assert '&lt;synthetic&gt;' in rendered and '<synthetic>' not in rendered
assert render_report_html(sample) == rendered
metadata = importlib.metadata.distribution('costguard-agent')
assert Path(metadata.locate_file('')).resolve() == root
assert {'split', 'split-server'} <= set(metadata.metadata.get_all('Provides-Extra', []))
if a.claims or a.server:
    importlib.import_module('costguard_split.connectors')
    importlib.import_module('costguard_split.schemas.usage')
    from costguard_split.ingest.pricing_public import _TABLE_PATH, _load_table
    assert _TABLE_PATH.resolve().is_relative_to(root)
    version, models = _load_table(_TABLE_PATH)
    assert version and models
if a.server:
    from costguard_split.api.app import create_app
    from fastapi.testclient import TestClient
    with tempfile.TemporaryDirectory() as td:
        with TestClient(create_app(db_path=Path(td) / 'synthetic.db')) as client:
            response = client.get('/api/v1/visualization/summary', params={
                'org_id': 'synthetic-org', 'start': '2026-01-01T00:00:00Z',
                'end': '2026-01-02T00:00:00Z'})
            assert response.status_code == 404
            response = client.get('/healthz')
            assert response.status_code == 200
for name, module in list(sys.modules.items()):
    if name.startswith(('costguard_split', 'costguard_agent')) and getattr(module, '__file__', None):
        assert Path(module.__file__).resolve().is_relative_to(root), name
print(json.dumps({'installed_split': 'PASS', 'pricing_resource': 'PASS', 'offline_html': 'PASS',
                  'claims': 'PASS' if a.claims or a.server else 'not requested (requires [split])',
                  'server': 'PASS' if a.server else 'not requested', 'source_fallback': False}))
