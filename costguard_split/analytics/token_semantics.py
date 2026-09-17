"""Opt-in v1 token semantics, based on declared collector version.

Original counters and legacy totals remain unchanged. A collector label is a
client declaration, not proof of provenance or provider billing accuracy.
Unknown declarations must never yield a guessed comparable token total.
"""
from collections import defaultdict

COUNTERS = ('input_tokens', 'cached_input_tokens', 'cache_write_tokens',
            'output_tokens', 'reasoning_tokens')
HERMES_VERSION = 'hermes-cumulative-v1'


def token_semantics_summary(db, organization_id, start, end, *, provider=None,
                            model=None, member_id=None, device_id=None):
    query = '''SELECT collector_version, request_count, input_tokens,
        cached_input_tokens, cache_write_tokens, output_tokens, reasoning_tokens
        FROM usage_events WHERE organization_id = ?
        AND started_at >= ? AND started_at < ?'''
    params = [organization_id, start, end]
    for name, value in (('provider', provider), ('model', model),
                        ('member_id', member_id), ('device_id', device_id)):
        if value is not None:
            query += ' AND ' + name + ' = ?'
            params.append(value)
    return summarize_token_rows(db.execute(query, params))


def summarize_token_rows(rows):
    """Summarize a single snapshot of (version, requests, five counters)."""
    groups = defaultdict(lambda: dict(events=0, request_count=0,
                                      **{key: 0 for key in COUNTERS}))
    for row in rows:
        version = row[0]
        group = groups[version]
        group['events'] += 1
        group['request_count'] += row[1]
        for key, value in zip(COUNTERS, row[2:]):
            group[key] += value
    result = []
    for version, group in sorted(groups.items(), key=lambda item: (item[0] is not None, item[0] or '')):
        known = version == HERMES_VERSION
        result.append(dict(collector_version=version,
            semantics='hermes-canonical-v1' if known else 'unknown',
            **group,
            token_total_nullable=sum(group[k] for k in COUNTERS[:-1]) if known else None))
    unknown = sum(g['events'] for g in result if g['semantics'] == 'unknown')
    return dict(schema_version='1', basis='declared-collector-version',
        events=sum(g['events'] for g in result),
        request_count=sum(g['request_count'] for g in result),
        unknown_semantics_events=unknown,
        token_total_nullable=None if unknown else sum(g['token_total_nullable'] for g in result),
        groups=result)
