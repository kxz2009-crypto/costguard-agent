import concurrent.futures
from datetime import datetime
from pathlib import Path
import sqlite3
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from costguard_split.collection.hermes import HermesIncremental, SourceRegression, FIELDS, SQL
from costguard_split.api.app import create_app
from costguard_split.api.context import ServerContext

UID='cgdev_00000000-0000-4000-8000-000000000066'

@pytest.fixture
def source(tmp_path):
    root=tmp_path/'source';root.mkdir();p=root/'state.db'
    with sqlite3.connect(p) as db:
        db.execute('CREATE TABLE session_model_usage(session_id TEXT,model TEXT,billing_provider TEXT,api_call_count INTEGER,input_tokens INTEGER,output_tokens INTEGER,cache_read_tokens INTEGER,cache_write_tokens INTEGER,reasoning_tokens INTEGER,first_seen REAL,last_seen REAL,task TEXT)')
        db.execute("INSERT INTO session_model_usage VALUES ('private-session','synthetic-model','synthetic',2,100,20,3,4,5,1000,1010,'PRIVATE-TASK-MUST-NOT-BE-READ')")
    return p

def update(source, **values):
    with sqlite3.connect(source) as db:
        db.execute('UPDATE session_model_usage SET '+','.join(k+'=?' for k in values),tuple(values.values()))

def collector(source,tmp_path):return HermesIncremental(source,tmp_path/'state',UID)


def test_initial_baseline_delta_replay_and_reopen(source,tmp_path):
    c=collector(source,tmp_path)
    assert c.scan()['queued']==0
    update(source,api_call_count=3,input_tokens=120,output_tokens=27,last_seen=1020)
    assert c.scan()['queued']==1
    first=c.pending()[0]
    assert (first.input_tokens,first.output_tokens,first.request_count)==(20,7,1)
    assert 'private-session' not in first.model_dump_json()
    assert c.scan()['queued']==0
    again=collector(source,tmp_path)
    assert again.pending()==[first]
    assert again.scan()['queued']==0
    assert (tmp_path/'state').stat().st_mode & 0o777 == 0o700
    assert again.path.stat().st_mode & 0o777 == 0o600


def test_new_session_after_initial_scan_is_not_lost(source,tmp_path):
    c=collector(source,tmp_path);c.scan()
    with sqlite3.connect(source) as db:
        db.execute("INSERT INTO session_model_usage VALUES ('new-session','synthetic-model','synthetic',1,9,8,0,0,0,1030,1040,'private')")
    assert c.scan()['queued']==1
    assert c.pending()[0].input_tokens==9


def test_explicit_history_and_empty_source_initialization(source,tmp_path):
    c=collector(source,tmp_path)
    assert c.scan(include_history=True)['queued']==1
    assert c.pending()[0].input_tokens==100
    assert c.scan(include_history=True)['queued']==0


@pytest.mark.parametrize('values',[{'input_tokens':99},{'last_seen':1009},{'first_seen':1001}])
def test_regression_fails_without_advancing_checkpoint(source,tmp_path,values):
    c=collector(source,tmp_path);c.scan()
    update(source,**values)
    with pytest.raises(SourceRegression):c.scan()
    assert not c.pending()
    update(source,input_tokens=105,last_seen=1020,first_seen=1000)
    with pytest.raises(SourceRegression):collector(source,tmp_path).scan()
    c.resume_after_investigation()
    assert c.scan()['queued']==1
    assert c.pending()[0].input_tokens==5


def test_concurrent_scans_queue_delta_once(source,tmp_path):
    c=collector(source,tmp_path);c.scan()
    update(source,input_tokens=110,last_seen=1020)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        results=list(pool.map(lambda _:collector(source,tmp_path).scan(),range(6)))
    assert sum(r['queued'] for r in results)==1
    assert len(c.pending())==1


def test_source_metadata_only_and_no_source_write(source,tmp_path):
    before=source.read_bytes();c=collector(source,tmp_path)
    c.scan(include_history=True)
    assert source.read_bytes()==before
    assert 'task' not in SQL.lower() and 'url' not in SQL.lower()
    assert 'PRIVATE-TASK' not in c.path.read_bytes().decode('latin1')
    assert b'private-session' not in c.path.read_bytes()


def test_state_cannot_be_reused_for_other_device(source,tmp_path):
    collector(source,tmp_path)
    with pytest.raises(ValueError,match='different'):
        HermesIncremental(source,tmp_path/'state',UID.replace('066','067'))


def test_source_replacement_is_detected(source,tmp_path):
    c=collector(source,tmp_path);c.scan()
    other=source.with_name('replacement.db');other.write_bytes(source.read_bytes());other.replace(source)
    with pytest.raises(ValueError,match='replaced'):c.scan()


def test_source_replacement_between_validation_and_sqlite_open_rolls_back(source,tmp_path):
    c=collector(source,tmp_path);c.scan()
    update(source,input_tokens=110,last_seen=1020)
    replacement=source.with_name('replacement.db')
    replacement.write_bytes(source.read_bytes())
    update(replacement,input_tokens=999,last_seen=1030)
    with sqlite3.connect(c.path) as db:
        before={table:db.execute('SELECT * FROM '+table+' ORDER BY rowid').fetchall()
                for table in ('meta','streams','outbox')}
    real_connect=sqlite3.connect
    replaced=False
    def replace_during_connect(database,*args,**kwargs):
        nonlocal replaced
        if not replaced and ('/proc/self/fd/' in str(database) or
                             '/dev/fd/' in str(database)):
            replaced=True
            replacement.replace(source)
        return real_connect(database,*args,**kwargs)
    with patch('costguard_split.collection.hermes.sqlite3.connect',side_effect=replace_during_connect):
        with pytest.raises(ValueError,match='source (file was replaced|does not match)'):
            c.scan()
    assert replaced
    with sqlite3.connect(c.path) as db:
        after={table:db.execute('SELECT * FROM '+table+' ORDER BY rowid').fetchall()
               for table in ('meta','streams','outbox')}
    assert after==before


def test_checkpoint_cannot_alias_source(source,tmp_path):
    import os
    d=tmp_path/'state';d.mkdir()
    os.link(source,d/'checkpoint.sqlite3')
    with pytest.raises(ValueError,match='unsafe'):collector(source,tmp_path)


def test_real_server_lost_ack_retry_and_new_delta(source,tmp_path):
    c=collector(source,tmp_path);c.scan(include_history=True)
    app=create_app(tmp_path/'server.db',ServerContext('synthetic-org'))
    with TestClient(app) as client:
        assert client.post('/api/v1/devices/register',json={'device_uid':UID,'hostname_fingerprint':'hk1:'+'a'*32,'username_fingerprint':'hk1:'+'b'*32,'os':'synthetic','arch':'synthetic'}).status_code==201
        def lost(claim):
            assert client.post('/api/v1/usage/events',json=claim.model_dump(mode='json')).status_code==201
            raise TimeoutError('synthetic lost acknowledgement')
        with pytest.raises(TimeoutError):c.deliver(lost)
        assert len(c.pending())==1
        send=lambda claim:client.post('/api/v1/usage/events',json=claim.model_dump(mode='json'))
        assert collector(source,tmp_path).deliver(send)==1
        assert not c.pending()
        update(source,input_tokens=111,output_tokens=22,last_seen=1020)
        assert c.scan()['queued']==1
        assert c.deliver(send)==1
        with sqlite3.connect(tmp_path/'server.db') as db:
            assert db.execute('SELECT COUNT(*),SUM(input_tokens),SUM(output_tokens) FROM usage_events').fetchone()==(2,111,22)


def test_wrong_receipt_or_http_failure_keeps_outbox(source,tmp_path):
    from types import SimpleNamespace
    c=collector(source,tmp_path);c.scan(include_history=True)
    with pytest.raises(RuntimeError):c.deliver(lambda _:SimpleNamespace(status_code=500))
    with pytest.raises(RuntimeError):c.deliver(lambda _:SimpleNamespace(status_code=200,json=lambda:{'id':'x','device_uid':UID,'source_event_id':'wrong'}))
    assert len(c.pending())==1


def test_invalid_counter_rolls_back_entire_scan(source,tmp_path):
    c=collector(source,tmp_path);c.scan()
    update(source,input_tokens=110,last_seen=1020)
    with sqlite3.connect(source) as db:
        db.execute("INSERT INTO session_model_usage VALUES ('zz-invalid','model','synthetic',1,-1,0,0,0,0,1000,1020,'private')")
    with pytest.raises(ValueError):c.scan()
    assert not c.pending()
    with sqlite3.connect(source) as db:db.execute("DELETE FROM session_model_usage WHERE session_id='zz-invalid'")
    assert c.scan()['queued']==1
    assert c.pending()[0].input_tokens==10


def test_empty_source_then_new_session_is_imported(source,tmp_path):
    with sqlite3.connect(source) as db:db.execute('DELETE FROM session_model_usage')
    c=collector(source,tmp_path);assert c.scan()['queued']==0
    with sqlite3.connect(source) as db:
        db.execute("INSERT INTO session_model_usage VALUES ('new-session','model','synthetic',1,9,8,0,0,0,1030,1040,'private')")
    assert c.scan()['queued']==1


def test_additional_billing_rows_are_aggregated_without_reading_private_keys(source,tmp_path):
    c=collector(source,tmp_path);c.scan()
    with sqlite3.connect(source) as db:
        db.execute("INSERT INTO session_model_usage VALUES ('private-session','synthetic-model','synthetic',1,9,8,0,0,0,1020,1040,'OTHER-PRIVATE-TASK')")
    assert c.scan()['queued']==1
    claim=c.pending()[0]
    assert (claim.input_tokens,claim.output_tokens,claim.request_count)==(9,8,1)


def test_zero_unobserved_source_row_is_reported(source,tmp_path):
    with sqlite3.connect(source) as db:
        db.execute("INSERT INTO session_model_usage VALUES ('empty','model','synthetic',0,0,0,0,0,0,NULL,NULL,'private')")
    c=collector(source,tmp_path)
    assert c.scan()['empty_unobserved']==1


def test_provider_identity_never_collapses_null_empty_unknown(source,tmp_path):
    with sqlite3.connect(source) as db:
        db.execute('DELETE FROM session_model_usage')
        for provider in (None,'','unknown'):
            db.execute("INSERT INTO session_model_usage VALUES ('same','model',?,1,10,0,0,0,0,1000,1010,'private')",(provider,))
    c=collector(source,tmp_path)
    assert c.scan(include_history=True)['queued']==3
    assert len({p.source_event_id for p in c.pending()})==3
    assert sum(p.input_tokens for p in c.pending())==30


def test_observed_stream_empty_reset_is_durably_halted(source,tmp_path):
    c=collector(source,tmp_path);c.scan()
    update(source,api_call_count=0,input_tokens=0,output_tokens=0,cache_read_tokens=0,cache_write_tokens=0,reasoning_tokens=0,first_seen=None,last_seen=None)
    with pytest.raises(SourceRegression):c.scan()
    update(source,api_call_count=3,input_tokens=110,output_tokens=25,cache_read_tokens=3,cache_write_tokens=4,reasoning_tokens=5,first_seen=1000,last_seen=1020)
    with pytest.raises(SourceRegression,match='halted'):collector(source,tmp_path).scan()
    assert not c.pending()
    c.resume_after_investigation();assert c.scan()['queued']==1
    assert c.pending()[0].input_tokens==10


@pytest.mark.parametrize('kind',['symlink','hardlink','replacement','directory'])
def test_checkpoint_replacement_after_construction_is_rejected(source,tmp_path,kind):
    import os
    c=collector(source,tmp_path);c.scan();before=source.read_bytes()
    if kind=='directory':
        c.state.rename(tmp_path/'old-state');c.state.mkdir(mode=0o700)
    else:
        c.path.unlink()
        if kind=='symlink':c.path.symlink_to(source)
        elif kind=='hardlink':os.link(source,c.path)
        else:c.path.write_bytes(b'not-a-checkpoint')
    with pytest.raises((ValueError,OSError)):c.scan()
    assert source.read_bytes()==before


def test_delivery_does_not_resume_while_halted(source,tmp_path):
    c=collector(source,tmp_path);c.scan(include_history=True)
    update(source,input_tokens=99)
    with pytest.raises(SourceRegression):c.scan()
    from unittest.mock import Mock
    send=Mock()
    with pytest.raises(SourceRegression):c.deliver(send)
    send.assert_not_called()
    assert len(c.pending())==1


def test_pre_review_state_schema_rejected_without_reset(source,tmp_path):
    c=collector(source,tmp_path);c.scan();c.close()
    with sqlite3.connect(tmp_path/'state/checkpoint.sqlite3') as db:
        db.execute("UPDATE meta SET value='1' WHERE key='schema_version'")
    with pytest.raises(ValueError,match='unsupported checkpoint schema'):collector(source,tmp_path)
    with sqlite3.connect(tmp_path/'state/checkpoint.sqlite3') as db:
        assert db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0]=='1'
