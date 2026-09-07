"""P1B-01 OPEN analytics read service.

Read-only aggregation over usage_events.

Rules:
- usage_events is the only source of truth
- no mutation
- no repricing
- no HTTP
- no cache
- no materialized view
- no private intelligence
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation

from .dto import AnalyticsSummary, DimensionSummary, UsageTotals


_TOKEN_COLUMNS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_tokens",
    "output_tokens",
    "reasoning_tokens",
)


def _cost_sum(rows) -> str | None:
    """
    Sum already stored public estimates only.

    NULL stays NULL if any event has incomplete money data.
    No recalculation.
    """
    values = []

    for row in rows:
        value = row["api_equivalent_cost_usd"]
        if value is None:
            return None
        try:
            values.append(Decimal(value))
        except InvalidOperation:
            return None

    if not values:
        return None

    return str(sum(values).quantize(Decimal("0.0001")))


def _dimension(rows, key_index: int):
    result = defaultdict(
        lambda: {
            "events": 0,
            "request_count": 0,
            **{k: 0 for k in _TOKEN_COLUMNS},
        }
    )

    for row in rows:
        key = row[key_index]
        if key is None:
            key = None

        item = result[key]
        item["events"] += 1
        item["request_count"] += row["request_count"]

        for col in _TOKEN_COLUMNS:
            item[col] += row[col]

    return [
        DimensionSummary(
            key="" if key is None else str(key),
            events=value["events"],
            request_count=value["request_count"],
            **{
                col: value[col]
                for col in _TOKEN_COLUMNS
            },
        )
        for key, value in sorted(
            result.items(),
            key=lambda x: x[1]["events"],
            reverse=True,
        )
    ]


def analytics_summary(
    db,
    organization_id: str,
    start: str,
    end: str,
    provider: str | None = None,
    model: str | None = None,
    member_id: str | None = None,
    device_id: str | None = None,
) -> AnalyticsSummary:
    """
    Build read-only usage analytics summary.

    Time semantics:
        started_at >= start AND started_at < end
    """

    query = """
    SELECT
        provider,
        model,
        member_id,
        device_id,
        request_count,
        input_tokens,
        cached_input_tokens,
        cache_write_tokens,
        output_tokens,
        reasoning_tokens,
        api_equivalent_cost_usd
    FROM usage_events
    WHERE organization_id = ?
      AND started_at >= ?
      AND started_at < ?
    """

    params = [
        organization_id,
        start,
        end,
    ]

    if provider is not None:
        query += " AND provider = ?"
        params.append(provider)

    if model is not None:
        query += " AND model = ?"
        params.append(model)

    if member_id is not None:
        query += " AND member_id = ?"
        params.append(member_id)

    if device_id is not None:
        query += " AND device_id = ?"
        params.append(device_id)

    rows = db.execute(query, params).fetchall()

    totals = UsageTotals(
        events=len(rows),
        request_count=sum(r["request_count"] for r in rows),
        input_tokens=sum(r["input_tokens"] for r in rows),
        cached_input_tokens=sum(r["cached_input_tokens"] for r in rows),
        cache_write_tokens=sum(r["cache_write_tokens"] for r in rows),
        output_tokens=sum(r["output_tokens"] for r in rows),
        reasoning_tokens=sum(r["reasoning_tokens"] for r in rows),
        public_cost_sum_nullable=_cost_sum(rows),
    )

    return AnalyticsSummary(
        totals=totals,
        by_provider=_dimension(rows, 0),
        by_model=_dimension(rows, 1),
        by_member=_dimension(rows, 2),
        by_device=_dimension(rows, 3),
    )
