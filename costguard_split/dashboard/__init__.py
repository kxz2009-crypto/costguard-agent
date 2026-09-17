"""P1D-02 OPEN dashboard read projection.

Dashboard-ready read models assembled from existing layers.

No external storage access.
No pricing logic.
No private intelligence.
"""

from costguard_split.dashboard.dto import DashboardMeta, DashboardPayload
from costguard_split.dashboard.service import (
    SCHEMA_VERSION,
    dashboard_projection,
)

__all__ = [
    "DashboardMeta",
    "DashboardPayload",
    "SCHEMA_VERSION",
    "dashboard_projection",
]
