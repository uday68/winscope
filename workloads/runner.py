"""
WinScope - Experiment Runner.

Orchestrates multi-phase performance experiments (Pre-baseline -> Workload -> Recovery),
records environment metadata, coordinates telemetry collection, and triggers database ingestion.
"""

import os
import time
import uuid
import json
import threading
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from collector.python.collector import WindowsTelemetryCollector
from workloads.scenarios import (
    BaseWorkload,
    IdleBaselineWorkload,
    CpuStressWorkload,
    MemoryAllocationWorkload,
    DiskIoWorkload
)
from ingestion.pipeline import TelemetryIngestionPipeline
from ingestion.quality import DataQualityReport
from storage.db import TelemetryDatabase


class PerformanceExperimentRunner:
    """
    Coordinates controlled experiment execution and synchronous telemetry collection.
    """

    def __init__(
        self,
        db: Optional[TelemetryDatabase] = None,
        raw_output_dir: Optional[str] = None
    ):
        self.db = db or TelemetryDatabase()
        self.pipeline = TelemetryIngestionPipeline(self.db)
        self.raw_output_dir = raw_output_dir or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "data", "raw")
        )
        os.makedirs(self.raw_output_dir, exist_ok=True)

    def run_experiment(
        self,
        workload: BaseWorkload,
        pre_baseline_sec: int = 2,
        post_recovery_sec: int = 2,
        sampling_interval_ms: int = 1000,
        is_baseline: bool = False
    ) -> Dict[str, Any]:
        """
        Executes an experiment across three consecutive temporal phases:
        1. Pre-baseline (ambient measurement)
        2. Workload (active stimulus)
        3. Post-recovery (settling observation)
        """
        experiment_id = str(uuid.uuid4())
        session_file = os.path.join(self.raw_output_dir, f"exp_{experiment_id}.jsonl")
        total_duration = pre_baseline_sec + workload.duration_sec + post_recovery_sec

        collector = WindowsTelemetryCollector(
            sampling_interval_ms=sampling_interval_ms,
            target_pid=os.getpid()
        )

        experiment_meta = {
            "experiment_id": experiment_id,
            "workload_name": workload.name,
            "is_baseline": is_baseline,
            "pre_baseline_sec": pre_baseline_sec,
            "workload_duration_sec": workload.duration_sec,
            "post_recovery_sec": post_recovery_sec,
            "sampling_interval_ms": sampling_interval_ms,
            "start_time": datetime.now(timezone.utc).isoformat(),
        }

        workload_result = {}

        def workload_thread_target():
            time.sleep(pre_baseline_sec)
            nonlocal workload_result
            workload_result = workload.execute()

        # Start workload thread
        wl_thread = threading.Thread(target=workload_thread_target, daemon=True)
        wl_thread.start()

        # Execute collector synchronously on calling thread
        collector.run_session(duration_seconds=total_duration, output_file=session_file)
        wl_thread.join()

        experiment_meta["end_time"] = datetime.now(timezone.utc).isoformat()
        experiment_meta["workload_result"] = workload_result

        # Ingest session into durable storage
        quality_report = self.pipeline.ingest_file(session_file)

        return {
            "metadata": experiment_meta,
            "session_file": session_file,
            "quality_report": quality_report
        }
