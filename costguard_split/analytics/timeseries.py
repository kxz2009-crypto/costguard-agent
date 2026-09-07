"""P1C-01 OPEN time series analytics.

Read-only time bucket aggregation.

Rules:
- usage_events read only
- no mutation
- no cost recalculation
- no private intelligence
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from .timeseries_dto import TimeSeriesPoint


_TOKEN_COLUMNS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_tokens",
    "output_tokens",
    "reasoning_tokens",
)


def _bucket_start(value: str, granularity: str) -> datetime:
    dt = datetime.fromisoformat(value)

    if granularity == "hour":
        return dt.replace(
            minute=0,
            second=0,
            microsecond=0,
        )

    if granularity == "day":
        return dt.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

    raise ValueError("unsupported granularity")


def _bucket_end(start: datetime, granularity: str) -> datetime:
    if granularity == "hour":
        return start + timedelta(hours=1)

    return start + timedelta(days=1)


def _cost(values):
    result = []

    for value in values:
        if value is None:
            return None

        try:
            result.append(Decimal(value))
        except InvalidOperation:
            return None

    if not result:
        return None

    return str(
        sum(result).quantize(
            Decimal("0.0001")
        )
    )


def timeseries_summary(
    db,
    organization_id: str,
    start: str,
    end: str,
    granularity: str,
) -> list[TimeSeriesPoint]:

    rows = db.execute(
        """
        SELECT
            started_at,
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
        """,
        (
            organization_id,
            start,
            end,
        ),
    ).fetchall()

    buckets = defaultdict(list)

    for row in rows:
        bucket = _bucket_start(
            row["started_at"],
            granularity,
        )
        buckets[bucket].append(row)

    result = []

    for bucket in sorted(buckets):

        rows_in_bucket = buckets[bucket]

        result.append(
            TimeSeriesPoint(
                bucket_start=bucket.isoformat(),
                bucket_end=_bucket_end(
                    bucket,
                    granularity,
                ).isoformat(),

                events=len(rows_in_bucket),

                request_count=sum(
                    r["request_count"]
                    for r in rows_in_bucket
                ),

                input_tokens=sum(
                    r["input_tokens"]
                    for r in rows_in_bucket
                ),

                cached_input_tokens=sum(
                    r["cached_input_tokens"]
                    for r in rows_in_bucket
                ),

                cache_write_tokens=sum(
                    r["cache_write_tokens"]
                    for r in rows_in_bucket
                ),

                output_tokens=sum(
                    r["output_tokens"]
                    for r in rows_in_bucket
                ),

                reasoning_tokens=sum(
                    r["reasoning_tokens"]
                    for r in rows_in_bucket
                ),

                public_cost_nullable=_cost(
                    [
                        r["api_equivalent_cost_usd"]
                        for r in rows_in_bucket
                    ]
                ),
            )
        )

    return result
