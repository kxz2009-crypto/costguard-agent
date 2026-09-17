"""Missing context and cross-org requests must fail before legacy reads."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from costguard_split.api.app import create_app
from costguard_split.api.context import ServerContext

ROUTES = [
    ('summary', 'costguard_split.api.visualization.analytics_summary'),
    ('providers', 'costguard_split.api.visualization.analytics_summary'),
    ('models', 'costguard_split.api.visualization.analytics_summary'),
    ('trend', 'costguard_split.api.trend_visualization.timeseries_summary'),
]


@pytest.mark.parametrize('route,service', ROUTES)
@pytest.mark.parametrize('context', [None, ServerContext('other-org')])
def test_legacy_read_denies_untrusted_org_before_service(tmp_path, route, service, context):
    app = create_app(db_path=tmp_path / 'synthetic.db', context=context)
    with patch(service, side_effect=AssertionError('unauthorized read')) as read:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get('/api/v1/visualization/' + route, params={
                'org_id': 'requested-org', 'start': '2026-01-01T00:00:00+00:00',
                'end': '2026-01-02T00:00:00+00:00', 'interval': 'day',
            })
        assert response.status_code == 404
        assert response.json() == {'detail': 'not found'}
        read.assert_not_called()


@pytest.mark.parametrize('route,service', ROUTES)
def test_legacy_read_keeps_matching_context_working(tmp_path, route, service):
    app = create_app(db_path=tmp_path / 'synthetic.db', context=ServerContext('requested-org'))
    with TestClient(app) as client:
        response = client.get('/api/v1/visualization/' + route, params={
            'org_id': 'requested-org', 'start': '2026-01-01T00:00:00+00:00',
            'end': '2026-01-02T00:00:00+00:00', 'interval': 'day',
        })
    assert response.status_code == 200
