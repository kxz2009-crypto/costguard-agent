"""P1E revision B: synthetic-only renderer acceptance checks E1-E13."""
import ast
from copy import deepcopy
from dataclasses import fields, replace
from html.parser import HTMLParser
import importlib
from pathlib import Path
from unittest.mock import patch

import pytest

from costguard_split.report.dto import ReportDocument, ReportMeta


class Parsed(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.text = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.text.append(data)


def renderer():
    return importlib.import_module('costguard_split.presentation.html_report').render_report_html


def document():
    return ReportDocument(ReportMeta('schema-synthetic', 'baseline-synthetic',
        '2026-01-01', '2026-01-02', 'day', 'provider-synthetic', 'model-synthetic',
        'member-synthetic', 'device-synthetic'), '# Synthetic report\n你好 & café', 'body-hash-synthetic')


def test_e1_e2_e4_e11_e13_document_shape_values_integrity():
    render = renderer()
    doc = document()
    before = deepcopy(doc.to_dict())
    html = render(doc)
    assert html.lower().startswith('<!doctype html>')
    parsed = Parsed(html)
    tags = [tag for tag, _ in parsed.tags]
    assert all(tag in tags for tag in ('html', 'head', 'title', 'body', 'main', 'dl', 'pre'))
    text = ''.join(parsed.text)
    for field in fields(doc.meta):
        assert getattr(doc.meta, field.name) in text
    assert doc.body in text and doc.content_hash in text
    assert 'Report body content hash' in text
    assert 'does not cover this HTML' in text
    assert render(doc).encode('utf-8') == html.encode('utf-8')
    assert doc.to_dict() == before


HOSTILE = '\"><script>alert(1)</script><img src="https://example.invalid/a" onerror="x"> & \' //example.invalid/ 你好'


@pytest.mark.parametrize('field', [f.name for f in fields(ReportMeta)] + ['body', 'content_hash'])
def test_e5_e6_e7_e12_e13_each_dynamic_value_is_inert(field):
    doc = document()
    doc = replace(doc, **{field: HOSTILE}) if field in ('body', 'content_hash') else replace(doc, meta=replace(doc.meta, **{field: HOSTILE}))
    html = renderer()(doc)
    parsed = Parsed(html)
    assert HOSTILE in ''.join(parsed.text)
    assert HOSTILE not in html
    for tag, attrs in parsed.tags:
        assert tag not in {'script', 'form', 'iframe', 'object', 'embed', 'img', 'link', 'a', 'base', 'input', 'svg', 'math'}
        assert not any(k.startswith('on') or k in {'src', 'href', 'srcset', 'action', 'formaction', 'http-equiv'} for k in attrs)
    style_start = html.index('<style>') + len('<style>')
    style = html[style_start:html.index('</style>')].lower()
    assert 'url(' not in style and '@import' not in style and '@font-face' not in style


def test_e12_nullable_empty_and_unicode():
    doc = ReportDocument(ReportMeta('v', '基线', 'a', 'b'))
    html = renderer()(doc)
    text = ''.join(Parsed(html).text)
    assert text.count('Not specified') == 5
    assert '基线' in text
    assert '<pre' in html
    assert renderer()(doc) == html
    # Empty strings are preserved, not treated as None.
    empty = replace(doc, meta=replace(doc.meta, provider=''))
    assert ''.join(Parsed(renderer()(empty)).text).count('Not specified') == 4


def test_e3_e8_e9_no_io_or_ambient_inputs(tmp_path, monkeypatch):
    render = renderer()
    doc = document()
    expected = render(doc)
    before = list(tmp_path.rglob('*'))
    monkeypatch.chdir(tmp_path)
    targets = ['builtins.open', 'io.open', 'os.open', 'os.getenv',
        'time.time', 'time.localtime', 'random.random', 'socket.socket',
        'socket.create_connection', 'socket.gethostname', 'subprocess.Popen',
        'sqlite3.connect', 'webbrowser.open']
    from contextlib import ExitStack
    with ExitStack() as stack:
        for name in targets:
            stack.enter_context(patch(name, side_effect=AssertionError(name)))
        stack.enter_context(patch.dict('os.environ', {'TZ': 'Pacific/Honolulu', 'LANG': 'synthetic'}))
        assert render(doc) == expected
    assert list(tmp_path.rglob('*')) == before


def test_e10_import_and_call_boundary():
    module = importlib.import_module('costguard_split.presentation.html_report')
    tree = ast.parse(Path(module.__file__).read_text())
    allowed = {'__future__', 'html', 'costguard_split.report.dto'}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name in allowed for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module in allowed
        elif isinstance(node, ast.Call):
            assert not isinstance(node.func, ast.Attribute)
            assert isinstance(node.func, ast.Name)
            assert node.func.id in {'escape', '_text'}
