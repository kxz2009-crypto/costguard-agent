"""P1B-02 OPEN visualization service.

Presentation projection over analytics read model.

Rules:
- no external storage access
- no SQL
- no pricing calculation
- no mutation
"""

from __future__ import annotations

from ..analytics.dto import AnalyticsSummary

from .dto import (
    DistributionPoint,
    VisualizationSummary,
)


def _tokens(item) -> int:
    return (
        item.input_tokens
        + item.cached_input_tokens
        + item.cache_write_tokens
        + item.output_tokens
        + item.reasoning_tokens
    )


def provider_distribution(
    analytics: AnalyticsSummary,
) -> list[DistributionPoint]:

    return [
        DistributionPoint(
            dimension="provider",
            key=item.key,
            events=item.events,
            tokens=_tokens(item),
        )
        for item in analytics.by_provider
    ]


def model_distribution(
    analytics: AnalyticsSummary,
) -> list[DistributionPoint]:

    return [
        DistributionPoint(
            dimension="model",
            key=item.key,
            events=item.events,
            tokens=_tokens(item),
        )
        for item in analytics.by_model
    ]


def visualization_summary(
    analytics: AnalyticsSummary,
) -> VisualizationSummary:

    return VisualizationSummary(
        events=analytics.totals.events,
        tokens=_tokens(analytics.totals),
        public_cost_nullable=(
            analytics.totals.public_cost_sum_nullable
        ),
    )
