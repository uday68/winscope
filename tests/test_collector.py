"""
Tests for WindowsTelemetryCollector (Python and C# native binary).
"""

import os
import json
import tempfile
import pytest
from core.models import MetricObservation
from collector.python.collector import WindowsTelemetryCollector


def test_collector_single_snapshot():
    """Verify live system snapshot gathers expected metrics with valid values."""
    collector = WindowsTelemetryCollector(sampling_interval_ms=500)
    records = collector.collect_single_snapshot()

    assert len(records) >= 5
    metric_names = {r.metric_name for r in records}

    assert "cpu.utilization.pct" in metric_names
    assert "memory.physical.utilization.pct" in metric_names
    assert "memory.physical.available.bytes" in metric_names
    assert "system.uptime.seconds" in metric_names
    assert "collector.health.status" in metric_names

    for r in records:
        r.validate_against_catalog()
        assert r.timestamp.tzinfo is not None
        if r.status == "ok":
            assert r.value is not None


def test_collector_nonexistent_pid_failure_handling():
    """Verify collector gracefully handles invalid/dead PID without crashing or emitting fake 0.0."""
    non_existent_pid = 9999999
    collector = WindowsTelemetryCollector(sampling_interval_ms=500, target_pid=non_existent_pid)
    records = collector.collect_single_snapshot()

    proc_records = [r for r in records if r.metric_name.startswith("process.")]
    assert len(proc_records) > 0
    for pr in proc_records:
        assert pr.status in ("unavailable", "error")
        assert pr.value is None
        assert pr.error_message is not None


def test_collector_session_bounded_run():
    """Test running a bounded 2-second collection session writing to a temporary file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out_file = os.path.join(tmpdir, "test_session.jsonl")
        collector = WindowsTelemetryCollector(sampling_interval_ms=500)
        metadata = collector.run_session(duration_seconds=2, output_file=out_file)

        assert os.path.exists(out_file)
        assert metadata.end_time is not None
        assert metadata.end_time >= metadata.start_time

        with open(out_file, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]

        assert len(lines) >= 3
        # First line is session header
        header = json.loads(lines[0])
        assert header.get("type") == "session_header"
        assert header.get("session_id") == metadata.session_id

        # Last line is session footer
        footer = json.loads(lines[-1])
        assert footer.get("type") == "session_footer"

        # Intermediate lines are valid MetricObservations
        for line in lines[1:-1]:
            data = json.loads(line)
            obs = MetricObservation.model_validate(data)
            obs.validate_against_catalog()


def test_csharp_native_binary_execution():
    """Test executing the compiled C# WinScope.Collector.exe if available."""
    csharp_bin = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "collector", "csharp", "bin", "WinScope.Collector.exe")
    )
    if not os.path.exists(csharp_bin):
        pytest.skip("WinScope.Collector.exe not yet compiled")

    with tempfile.TemporaryDirectory() as tmpdir:
        out_file = os.path.join(tmpdir, "csharp_session.jsonl")
        collector = WindowsTelemetryCollector(
            sampling_interval_ms=1000,
            use_native_binary=True,
            native_binary_path=csharp_bin
        )
        metadata = collector.run_session(duration_seconds=2, output_file=out_file)

        assert os.path.exists(out_file)
        with open(out_file, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]

        assert len(lines) >= 3
        header = json.loads(lines[0])
        assert header.get("type") == "session_header"
        assert header.get("collector_type") == "WinScope-CSharp-Native"
