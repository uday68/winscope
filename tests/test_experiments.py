"""
Tests for Workload Scenarios and Experiment Runner.
"""

import os
import tempfile
import pytest
from workloads.scenarios import (
    IdleBaselineWorkload,
    CpuStressWorkload,
    MemoryAllocationWorkload,
    DiskIoWorkload
)
from workloads.runner import PerformanceExperimentRunner
from storage.db import TelemetryDatabase


def test_cpu_stress_bounded_execution():
    wl = CpuStressWorkload(duration_sec=1, thread_count=1)
    res = wl.execute()
    assert res["workload"] == "cpu_stress"
    assert res["actual_duration_sec"] >= 0.8


def test_memory_workload_safe_allocation_and_release():
    wl = MemoryAllocationWorkload(duration_sec=1, target_mb=32)
    res = wl.execute()
    assert res["workload"] == "memory_pressure"
    assert res["allocated_mb"] == 32


def test_disk_io_workload_cleanup():
    wl = DiskIoWorkload(duration_sec=1, target_mb=10)
    res = wl.execute()
    assert res["workload"] == "disk_io"
    assert res["bytes_written"] > 0


def test_workload_cancellation():
    wl = CpuStressWorkload(duration_sec=10, thread_count=1)
    wl.stop()
    res = wl.execute()
    assert res["actual_duration_sec"] < 2.0


def test_experiment_runner_multiphase_run():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "exp_test.db")
        db = TelemetryDatabase(db_path)
        runner = PerformanceExperimentRunner(db=db, raw_output_dir=tmpdir)

        wl = IdleBaselineWorkload(duration_sec=1)
        res = runner.run_experiment(
            workload=wl,
            pre_baseline_sec=1,
            post_recovery_sec=1,
            sampling_interval_ms=500,
            is_baseline=True
        )

        assert os.path.exists(res["session_file"])
        assert res["quality_report"].accepted_records > 0
        assert res["metadata"]["is_baseline"] is True
