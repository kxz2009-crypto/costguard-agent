import sqlite3
import pytest
from fastapi.testclient import TestClient
from costguard_split.api.app import create_app
from costguard_split.api.context import ServerContext
BASE='/api/v1/consumption'
PARAMS=dict(org_id='a',start='2026-01-01T00:00:00Z',end='2026-02-01T00:00:00Z')
@pytest.fixture
def db_path(tmp_path):
 p=tmp_path/'test.db'
 with sqlite3.connect(p) as db:
  db.execute('''CREATE TABLE usage_events(id TEXT PRIMARY KEY,organization_id TEXT,provider TEXT,model TEXT,member_id TEXT,device_id TEXT,started_at TEXT,request_count INTEGER,input_tokens INTEGER,cached_input_tokens INTEGER,cache_write_tokens INTEGER,output_tokens INTEGER,reasoning_tokens INTEGER,api_equivalent_cost_usd TEXT,collector_version TEXT)''')
  db.executemany('INSERT INTO usage_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',[
   ('h','a','custom','hermes-model','member-h','device-h','2026-01-02T00:00:00+00:00',2,80,20,5,40,15,None,'hermes-cumulative-v1'),
   ('u','a','custom','unknown-model','member-u','device-u','2026-01-03T00:00:00+00:00',1,30,0,0,10,5,None,'legacy'),
   ('other','b','custom','hermes-model','member-h','device-h','2026-01-02T00:00:00+00:00',1,999,0,0,999,999,None,'hermes-cumulative-v1'),
   ('end','a','custom','hermes-model','member-h','device-h','2026-02-01T00:00:00+00:00',1,999,0,0,999,999,None,'hermes-cumulative-v1')])
 return p
@pytest.fixture
def client(db_path):
 with TestClient(create_app(db_path,ServerContext('a'))) as c:yield c

def get(c,**kw):return c.get(BASE+'/token-semantics',params=PARAMS|kw)

def test_known_native_total(client):
 r=get(client,model='hermes-model');assert r.status_code==200
 d=r.json();assert d['schema_version']=='1' and d['basis']=='declared-collector-version'
 assert d['events']==1 and d['request_count']==2 and d['token_total_nullable']==145
 assert d['groups'][0]['reasoning_tokens']==15 and d['groups'][0]['input_tokens']==80
 assert 'no-store' in r.headers['cache-control']

def test_mixed_sources(client):
 d=get(client).json();assert d['events']==2 and d['unknown_semantics_events']==1
 assert d['token_total_nullable'] is None
 assert {g['semantics'] for g in d['groups']}=={'hermes-canonical-v1','unknown'}

@pytest.mark.parametrize('version',['','hermes-cumulative-v2','claude-v1','codex-v1',None])
def test_unrecognized_versions(client,db_path,version):
 with sqlite3.connect(db_path) as db:db.execute('UPDATE usage_events SET collector_version=? WHERE id=?',(version,'h'))
 d=get(client,model='hermes-model').json();assert d['token_total_nullable'] is None and d['unknown_semantics_events']==1

@pytest.mark.parametrize('filters',[{'model':'hermes-model'},{'device_id':'device-h'},{'member_id':'member-h'}])
def test_filters_and_end(client,filters):assert get(client,**filters).json()['token_total_nullable']==145

def test_empty_injection(client):
 d=get(client,provider="custom' OR 1=1 --").json();assert d['events']==0 and d['groups']==[] and d['token_total_nullable']==0

def test_tenant(client,db_path):
 assert get(client,org_id='b').status_code==404
 with TestClient(create_app(db_path,None)) as c:assert get(c).status_code==404

@pytest.mark.parametrize('kw',[{'start':'2026-01-01'},{'end':'2026-03-01T00:00:00Z'},{'end':PARAMS['start']}])
def test_windows(client,kw):assert get(client,**kw).status_code==400

def test_old_contract_read_only(client,db_path):
 def snap():
  with sqlite3.connect(db_path) as db:return db.execute('SELECT * FROM usage_events ORDER BY id').fetchall()
 before=snap();report=client.get(BASE+'/report/summary',params=PARAMS|{'model':'hermes-model'}).json()
 assert '| 1 | 160 |' in report['body']
 get(client);assert snap()==before
 assert client.get(BASE+'/report/summary',params=PARAMS|{'model':'hermes-model'}).json()==report
