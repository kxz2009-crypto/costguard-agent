import sqlite3
import pytest
from tests.split_token_semantics_test import db_path as base_db_path, client, PARAMS, BASE
@pytest.fixture
def db_path(base_db_path):
 with sqlite3.connect(base_db_path) as db:
  db.execute('ALTER TABLE usage_events ADD COLUMN ended_at TEXT')
  db.execute('UPDATE usage_events SET ended_at=started_at')
 return base_db_path

def get(c,**kw):return c.get(BASE+'/token-analysis',params=PARAMS|kw)

def test_models_days_unknown_zeros(client):
 r=get(client);assert r.status_code==200 and 'no-store' in r.headers['cache-control'];d=r.json()
 assert len(d['days'])==31 and d['summary']['events']==2 and d['summary']['token_total_nullable'] is None
 assert d['models'][0]['model']=='hermes-model' and d['models'][0]['token_total_nullable']==145
 assert d['models'][1]['token_total_nullable'] is None
 assert d['days'][1]['token_total_nullable']==145 and d['days'][2]['token_total_nullable'] is None
 assert d['days'][0]['events']==0 and d['days'][0]['token_total_nullable']==0
 assert sum(v['request_count'] for v in d['models'])==sum(v['request_count'] for v in d['days'])==d['summary']['request_count']
 assert d['summary']==client.get(BASE+'/token-semantics',params=PARAMS).json()

def test_cross_day_start_attribution(client,db_path):
 with sqlite3.connect(db_path) as db:db.execute("UPDATE usage_events SET ended_at='2026-01-04T01:00:00+00:00' WHERE id='h'")
 d=get(client,model='hermes-model').json()
 assert d['cross_day_events']==1 and d['day_basis']=='utc-observation-start'
 assert d['days'][1]['token_total_nullable']==145 and d['days'][3]['events']==0

def test_model_provider_pair(client,db_path):
 with sqlite3.connect(db_path) as db:db.execute("UPDATE usage_events SET model='hermes-model',provider='another' WHERE id='u'")
 d=get(client).json();assert len(d['models'])==2 and {m['provider'] for m in d['models']}=={'custom','another'}

def test_mixed_model_unknown(client,db_path):
 with sqlite3.connect(db_path) as db:db.execute("UPDATE usage_events SET model='hermes-model' WHERE id='u'")
 d=get(client).json();assert len(d['models'])==1 and d['models'][0]['token_total_nullable'] is None

@pytest.mark.parametrize('filters',[{'model':'hermes-model'},{'member_id':'member-h'},{'device_id':'device-h'}])
def test_filters(client,filters):
 d=get(client,**filters).json();assert d['summary']['events']==1 and d['summary']['token_total_nullable']==145

def test_tenant_empty_window(client):
 assert get(client,org_id='b').status_code==404
 assert get(client,start='bad').status_code==400
 assert get(client,end='2026-03-01T00:00:00Z').status_code==400
 d=get(client,provider="x' OR 1=1 --").json();assert d['summary']['events']==0 and d['models']==[] and len(d['days'])==31

def test_partial_day(client):
 d=get(client,start='2026-01-02T12:00:00Z',end='2026-01-03T12:00:00Z').json()
 assert [x['date'] for x in d['days']]==['2026-01-02','2026-01-03'] and d['summary']['events']==1
