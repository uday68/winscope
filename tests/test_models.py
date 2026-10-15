"""
Unit tests for WinScope data contracts, schema validation, and unit consistency.
"""

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from core.models import MetricObservation, SessionMetadata
from core.units import MetricUnit, TimeBasis, METRIC_CATALOG


def test_metric_observation_valid():
    """Test valid metric observation creation and UTC normalization."""
    now = datetime.now()
    obs = MetricObservation(
        timestamp=now,
        time_basis=TimeBasis.UTC_WALL_CLOCK,
        metric_name="cpu.utilization.pct",
        value=42.5,
        unit=MetricUnit.PERCENT,
        source="Win32_GetSystemTimes",
        status="ok"
    )
    assert obs.timestamp.tzinfo is not None
    assert obs.timestamp.tzinfo == timezone.utc
    assert obs.value == 42.5
    assert obs.status == "ok"
    obs.validate_against_catalog()


def test_metric_observation_unit_mismatch():
    """Test validation catches unit mismatch against catalog."""
    obs = MetricObservation(
        timestamp=datetime.now(timezone.utc),
        metric_name="cpu.utilization.pct",
        value=42.5,
        unit=MetricUnit.BYTES,  # Invalid: CPU cannot be bytes
        source="test",
        status="ok"
    )
    with pytest.raises(ValueError, match="Unit mismatch"):
        obs.validate_against_catalog()


def test_metric_observation_range_violation():
    """Test validation catches out-of-range values."""
    obs = MetricObservation(
        timestamp=datetime.now(timezone.utc),
        metric_name="cpu.utilization.pct",
        value=150.0,  # Invalid: > 100%
        unit=MetricUnit.PERCENT,
        source="test",
        status="ok"
    )
    with pytest.raises(ValueError, match="above maximum"):
        obs.validate_against_catalog()


def test_metric_observation_failure_never_emits_synthetic_zero():
    """
    Test requirement: Never silently convert collection failure to zero.
    Failed metric collection must preserve None value and descriptive error status.
    """
    obs = MetricObservation(
        timestamp=datetime.now(timezone.utc),
        metric_name="process.cpu.utilization.pct",
        value=None,
        unit=MetricUnit.PERCENT,
        source="ProcessTimes",
        target_id="PID:99999",
        status="unavailable",
        error_message="Process terminated"
    )
    assert obs.value is None
    assert obs.status == "unavailable"
    assert obs.error_message == "Process terminated"
    obs.validate_against_catalog()


def test_invalid_status_rejection():
    """Ensure arbitrary unrecognized statuses are rejected by schema."""
    with pytest.raises(ValidationError):
        MetricObservation(
            timestamp=datetime.now(timezone.utc),
            metric_name="cpu.utilization.pct",
            value=10.0,
            unit=MetricUnit.PERCENT,
            source="test",
            status="fabricated_status"
        )


def test_session_metadata_validation():
    """Ensure session metadata requires UUID, valid interval, and host."""
    meta = SessionMetadata(
        session_id="00000000-0000-0000-0000-000000000001",
        start_time=datetime.now(timezone.utc),
        host_name="TEST-HOST",
        os_version="Windows 11 Build 26100",
        sampling_interval_ms=1000
    )
    assert meta.sampling_interval_ms == 1000
    assert meta.collector_type == "WinScope-CSharp-Native"
