"""
WinScope - Telemetry Data Quality Analysis.

Assesses data integrity, duplicate counts, sampling interval regularity,
and missing intervals across ingested sessions.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import numpy as np
from pydantic import BaseModel, Field


class DataQualityReport(BaseModel):
    report_id: str
    session_id: str
    total_records: int
    accepted_records: int
    quarantined_records: int
    duplicate_records: int
    missing_intervals: int
    sampling_interval_expected_ms: int
    interval_mean_ms: Optional[float] = None
    interval_std_ms: Optional[float] = None
    interval_min_ms: Optional[float] = None
    interval_max_ms: Optional[float] = None
    unavailable_metrics: List[str] = Field(default_factory=list)
    quarantine_reasons: Dict[str, int] = Field(default_factory=dict)
    completeness_pct: float = Field(default=100.0)

    def summary_markdown(self) -> str:
        return f"""### Data Quality Report — Session `{self.session_id}`
- **Total Records Processed:** {self.total_records}
- **Accepted Observations:** {self.accepted_records} ({self.completeness_pct:.2f}% completeness)
- **Quarantined Records:** {self.quarantined_records}
- **Duplicate Observations:** {self.duplicate_records}
- **Detected Missing Intervals:** {self.missing_intervals}
- **Sampling Interval (Configured):** {self.sampling_interval_expected_ms} ms
- **Observed Interval (Mean ± Std):** {self.interval_mean_ms:.1f} ms ± {self.interval_std_ms:.1f} ms (Min: {self.interval_min_ms:.1f} ms, Max: {self.interval_max_ms:.1f} ms)
- **Unavailable Metrics:** {', '.join(self.unavailable_metrics) if self.unavailable_metrics else 'None'}
"""
