"""Read-only personal analysis from one query; days use UTC observation start.

Cumulative events cannot recover exact API-call times. A multi-day observation
is assigned to its start day, never apportioned as invented daily measurements.
"""
from collections import defaultdict
from datetime import datetime,timedelta,timezone
from .token_semantics import summarize_token_rows


def token_analysis(db,organization_id,start,end,*,provider=None,model=None,member_id=None,device_id=None):
    query='''SELECT collector_version,request_count,input_tokens,cached_input_tokens,
    cache_write_tokens,output_tokens,reasoning_tokens,provider,model,started_at,ended_at
    FROM usage_events WHERE organization_id=? AND started_at>=? AND started_at<?'''
    params=[organization_id,start,end]
    for name,value in (('provider',provider),('model',model),('member_id',member_id),('device_id',device_id)):
        if value is not None:query+=' AND '+name+'=?';params.append(value)
    rows=db.execute(query,params).fetchall()
    models=defaultdict(list);days=defaultdict(list);cross_day=0
    for row in rows:
        fact=tuple(row[:7]);models[(row[7],row[8])].append(fact)
        first=datetime.fromisoformat(row[9]).astimezone(timezone.utc)
        last=datetime.fromisoformat(row[10]).astimezone(timezone.utc)
        days[first.date().isoformat()].append(fact)
        cross_day+=first.date()!=last.date()
    daily=[];day=datetime.fromisoformat(start).astimezone(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0)
    stop=datetime.fromisoformat(end).astimezone(timezone.utc)
    while day<stop:
        key=day.date().isoformat();daily.append(dict(date=key,**summarize_token_rows(days[key])));day+=timedelta(days=1)
    by_model=[dict(provider=key[0],model=key[1],**summarize_token_rows(facts)) for key,facts in models.items()]
    by_model.sort(key=lambda g:(-g['request_count'],g['provider'] or '',g['model'] or ''))
    return dict(schema_version='1',window=dict(start=start,end=end),
                day_basis='utc-observation-start',cross_day_events=cross_day,
                summary=summarize_token_rows(tuple(row[:7]) for row in rows),
                models=by_model,days=daily)
