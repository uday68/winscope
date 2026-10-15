"""
WinScope - Core Data Contracts and Telemetry Schemas.

Enforces strict schemas for observations, missing-value semantics, and session metadata.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator
from core.units import MetricUnit, TimeBasis, METRIC_CATALOG


class MetricObservation(BaseModel):
    """
    Standard atomic telemetry observation record.
    Never emits synthetic zero for failed metric collections.
    """
    timestamp: datetime = Field(
        ...,
        description="UTC timestamp of the observation with ISO-8601 precision."
    )
    time_basis: TimeBasis = Field(
        default=TimeBasis.UTC_WALL_CLOCK,
        description="Reference clock basis for the observation timestamp."
    )
    metric_name: str = Field(
        ...,
        description="Canonical metric identifier matching METRIC_CATALOG."
    )
    value: Optional[float] = Field(
        default=None,
        description="Observed numeric value. None if status is not 'ok'."
    )
    unit: MetricUnit = Field(
        ...,
        description="Engineering unit of measurement."
    )
    source: str = Field(
        ...,
        description="Native API, counter, or subsystem providing the data."
    )
    target_id: Optional[str] = Field(
        default=None,
        description="Subject identifier if applicable (e.g., PID:1234, Disk:C)."
    )
    status: str = Field(
        default="ok",
        description="Collection status: 'ok', 'unavailable', 'error', 'degraded'."
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Diagnostic details if status is not 'ok'."
    )
    schema_version: str = Field(
        default="1.0.0",
        description="Semantic version of the observation schema."
    )

    @field_validator("timestamp")
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        valid_statuses = {"ok", "unavailable", "error", "degraded"}
        if v not in valid_statuses:
            raise ValueError(f"Invalid status '{v}'. Must be one of {valid_statuses}")
        return v

    def validate_against_catalog(self) -> None:
        """Validates metric against catalog units and valid ranges."""
        if self.metric_name in METRIC_CATALOG:
            spec = METRIC_CATALOG[self.metric_name]
            if self.unit != spec["unit"]:
                raise ValueError(
                    f"Unit mismatch for {self.metric_name}: expected {spec['unit']}, got {self.unit}"
                )
            if self.status == "ok" and self.value is not None:
                min_val, max_val = spec["valid_range"]
                if min_val is not None and self.value < min_val:
                    raise ValueError(
                        f"Value {self.value} below minimum {min_val} for {self.metric_name}"
                    )
                if max_val is not None and self.value > max_val:
                    raise ValueError(
                        f"Value {self.value} above maximum {max_val} for {self.metric_name}"
                    )


class SessionMetadata(BaseModel):
    """
    Metadata recording session provenance and collection parameters.
    """
    session_id: str = Field(..., description="Unique UUID identifying the collection session.")
    start_time: datetime = Field(..., description="UTC timestamp when collection began.")
    end_time: Optional[datetime] = Field(default=None, description="UTC timestamp when collection ended.")
    host_name: str = Field(..., description="Computer name where telemetry was gathered.")
    os_version: str = Field(..., description="Operating system release and build string.")
    sampling_interval_ms: int = Field(..., ge=50, description="Configured collection interval in milliseconds.")
    collector_type: str = Field(default="WinScope-CSharp-Native", description="Collector engine used.")
    collector_version: str = Field(default="1.0.0", description="Version of the WinScope collector.")
    schema_version: str = Field(default="1.0.0", description="Version of session metadata schema.")
