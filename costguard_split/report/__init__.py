"""P1D-03 OPEN report generation.

Deterministic static analytics reports from existing read models.

No external storage access.
No pricing logic.
No private intelligence.
"""

from costguard_split.report.dto import ReportDocument, ReportMeta
from costguard_split.report.service import (
    SCHEMA_VERSION,
    summary_report,
    timeseries_report,
)

__all__ = [
    "ReportDocument",
    "ReportMeta",
    "SCHEMA_VERSION",
    "summary_report",
    "timeseries_report",
]
