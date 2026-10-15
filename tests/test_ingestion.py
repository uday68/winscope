"""
Tests for TelemetryIngestionPipeline and SQLite storage.
"""

import os
import tempfile
import pytest
from storage.db import TelemetryDatabase
from ingestion.pipeline import TelemetryIngestionPipeline


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_winscope.db")
        db = TelemetryDatabase(db_path)
        yield db


def test_ingestion_valid_stream(temp_db):
    pipeline = TelemetryIngestionPipeline(temp_db)
    lines = [
        '{"type":"session_header","session_id":"test-s1","start_time":"2026-10-15T12:00:00Z","host_name":"TEST","os_version":"Win11","sampling_interval_ms":1000,"collector_type":"Native","collector_version":"1.0.0","schema_version":"1.0.0"}',
        '{"timestamp":"2026-10-15T12:00:01Z","time_basis":"utc_wall_clock","metric_name":"cpu.utilization.pct","value":10.5,"unit":"percent","source":"Win32","target_id":null,"status":"ok","error_message":null,"schema_version":"1.0.0"}',
        '{"timestamp":"2026-10-15T12:00:02Z","time_basis":"utc_wall_clock","metric_name":"cpu.utilization.pct","value":15.2,"unit":"percent","source":"Win32","target_id":null,"status":"ok","error_message":null,"schema_version":"1.0.0"}',
        '{"type":"session_footer","session_id":"test-s1","end_time":"2026-10-15T12:00:03Z","total_samples":2,"collector_status":"completed"}'
    ]

    report = pipeline.ingest_stream(lines)
    assert report.total_records == 4
    assert report.accepted_records == 2
    assert report.quarantined_records == 0
    assert report.duplicate_records == 0

    with temp_db.connection() as conn:
        obs = conn.execute("SELECT * FROM observations WHERE session_id = 'test-s1'").fetchall()
        assert len(obs) == 2


def test_ingestion_quarantines_malformed_and_duplicate(temp_db):
    pipeline = TelemetryIngestionPipeline(temp_db)
    lines = [
        '{"type":"session_header","session_id":"test-s2","start_time":"2026-10-15T12:00:00Z","host_name":"TEST","os_version":"Win11","sampling_interval_ms":1000,"collector_type":"Native","collector_version":"1.0.0","schema_version":"1.0.0"}',
        '{"timestamp":"2026-10-15T12:00:01Z","time_basis":"utc_wall_clock","metric_name":"cpu.utilization.pct","value":10.5,"unit":"percent","source":"Win32","target_id":null,"status":"ok","error_message":null,"schema_version":"1.0.0"}',
        # Duplicate record:
        '{"timestamp":"2026-10-15T12:00:01Z","time_basis":"utc_wall_clock","metric_name":"cpu.utilization.pct","value":10.5,"unit":"percent","source":"Win32","target_id":null,"status":"ok","error_message":null,"schema_version":"1.0.0"}',
        # Malformed JSON line:
        '{bad json',
        # Invalid unit:
        '{"timestamp":"2026-10-15T12:00:02Z","time_basis":"utc_wall_clock","metric_name":"cpu.utilization.pct","value":10.5,"unit":"invalid_unit","source":"Win32","target_id":null,"status":"ok","error_message":null,"schema_version":"1.0.0"}'
    ]

    report = pipeline.ingest_stream(lines)
    assert report.accepted_records == 1
    assert report.duplicate_records == 1
    assert report.quarantined_records == 3  # 1 duplicate + 1 json syntax error + 1 unit validation error

    with temp_db.connection() as conn:
        q_records = conn.execute("SELECT * FROM quarantined_records").fetchall()
        assert len(q_records) == 3


def test_ingestion_detects_missing_interval(temp_db):
    pipeline = TelemetryIngestionPipeline(temp_db)
    lines = [
        '{"type":"session_header","session_id":"test-s3","start_time":"2026-10-15T12:00:00Z","host_name":"TEST","os_version":"Win11","sampling_interval_ms":1000,"collector_type":"Native","collector_version":"1.0.0","schema_version":"1.0.0"}',
        '{"timestamp":"2026-10-15T12:00:01Z","time_basis":"utc_wall_clock","metric_name":"cpu.utilization.pct","value":10.0,"unit":"percent","source":"Win32","target_id":null,"status":"ok","error_message":null,"schema_version":"1.0.0"}',
        # Gap of 4 seconds (expected is 1 second)
        '{"timestamp":"2026-10-15T12:00:05Z","time_basis":"utc_wall_clock","metric_name":"cpu.utilization.pct","value":12.0,"unit":"percent","source":"Win32","target_id":null,"status":"ok","error_message":null,"schema_version":"1.0.0"}'
    ]

    report = pipeline.ingest_stream(lines)
    assert report.missing_intervals == 1
