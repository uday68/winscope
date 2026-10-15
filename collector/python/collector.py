"""
WinScope - Python Collector Engine and C# Process Orchestrator.

Provides both native Python collection (via psutil / pywin32) and
orchestration of the high-performance C# native collector executable.
"""

import os
import sys
import json
import time
import uuid
import socket
import platform
import subprocess
from datetime import datetime, timezone
from typing import Generator, Optional, Dict, Any, List

import psutil

from core.models import MetricObservation, SessionMetadata
from core.units import MetricUnit, TimeBasis, METRIC_CATALOG


class WindowsTelemetryCollector:
    """
    Collects live Windows system and process telemetry.
    Supports bounded runs, custom sampling intervals, and robust failure isolation.
    """

    def __init__(
        self,
        sampling_interval_ms: int = 1000,
        target_pid: Optional[int] = None,
        use_native_binary: bool = False,
        native_binary_path: Optional[str] = None
    ):
        self.sampling_interval_ms = max(100, sampling_interval_ms)
        self.target_pid = target_pid or os.getpid()
        self.use_native_binary = use_native_binary
        self.native_binary_path = native_binary_path or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "csharp", "bin", "WinScope.Collector.exe")
        )
        self._target_process: Optional[psutil.Process] = None
        self._init_target_process()
        self._prev_disk_io = None
        self._prev_disk_time = None

    def _init_target_process(self) -> None:
        try:
            self._target_process = psutil.Process(self.target_pid)
            # Prime CPU percent calculation
            self._target_process.cpu_percent(interval=None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            self._target_process = None

    def collect_single_snapshot(self) -> List[MetricObservation]:
        """
        Gathers one atomic snapshot across all supported system metrics.
        Never converts collection failure into a synthetic zero.
        """
        now = datetime.now(timezone.utc)
        records: List[MetricObservation] = []

        # 1. Total CPU Utilization
        try:
            cpu_val = psutil.cpu_percent(interval=None)
            records.append(
                MetricObservation(
                    timestamp=now,
                    time_basis=TimeBasis.UTC_WALL_CLOCK,
                    metric_name="cpu.utilization.pct",
                    value=cpu_val,
                    unit=MetricUnit.PERCENT,
                    source="psutil_cpu_percent",
                    status="ok"
                )
            )
        except Exception as ex:
            records.append(
                MetricObservation(
                    timestamp=now,
                    time_basis=TimeBasis.UTC_WALL_CLOCK,
                    metric_name="cpu.utilization.pct",
                    value=None,
                    unit=MetricUnit.PERCENT,
                    source="psutil_cpu_percent",
                    status="error",
                    error_message=str(ex)
                )
            )

        # 2. Physical Memory
        try:
            vm = psutil.virtual_memory()
            records.append(
                MetricObservation(
                    timestamp=now,
                    time_basis=TimeBasis.UTC_WALL_CLOCK,
                    metric_name="memory.physical.utilization.pct",
                    value=vm.percent,
                    unit=MetricUnit.PERCENT,
                    source="GlobalMemoryStatusEx",
                    status="ok"
                )
            )
            records.append(
                MetricObservation(
                    timestamp=now,
                    time_basis=TimeBasis.UTC_WALL_CLOCK,
                    metric_name="memory.physical.available.bytes",
                    value=float(vm.available),
                    unit=MetricUnit.BYTES,
                    source="GlobalMemoryStatusEx",
                    status="ok"
                )
            )
            records.append(
                MetricObservation(
                    timestamp=now,
                    time_basis=TimeBasis.UTC_WALL_CLOCK,
                    metric_name="memory.physical.total.bytes",
                    value=float(vm.total),
                    unit=MetricUnit.BYTES,
                    source="GlobalMemoryStatusEx",
                    status="ok"
                )
            )
        except Exception as ex:
            records.append(
                MetricObservation(
                    timestamp=now,
                    time_basis=TimeBasis.UTC_WALL_CLOCK,
                    metric_name="memory.physical.utilization.pct",
                    value=None,
                    unit=MetricUnit.PERCENT,
                    source="GlobalMemoryStatusEx",
                    status="error",
                    error_message=str(ex)
                )
            )

        # 3. Process CPU and Working Set
        if self._target_process:
            try:
                if not self._target_process.is_running():
                    records.append(
                        MetricObservation(
                            timestamp=now,
                            time_basis=TimeBasis.UTC_WALL_CLOCK,
                            metric_name="process.cpu.utilization.pct",
                            value=None,
                            unit=MetricUnit.PERCENT,
                            source="ProcessTimes",
                            target_id=f"PID:{self.target_pid}",
                            status="unavailable",
                            error_message="Process terminated"
                        )
                    )
                else:
                    proc_cpu = self._target_process.cpu_percent(interval=None)
                    mem_info = self._target_process.memory_info()
                    records.append(
                        MetricObservation(
                            timestamp=now,
                            time_basis=TimeBasis.UTC_WALL_CLOCK,
                            metric_name="process.cpu.utilization.pct",
                            value=proc_cpu,
                            unit=MetricUnit.PERCENT,
                            source="ProcessTimes",
                            target_id=f"PID:{self.target_pid}",
                            status="ok"
                        )
                    )
                    records.append(
                        MetricObservation(
                            timestamp=now,
                            time_basis=TimeBasis.UTC_WALL_CLOCK,
                            metric_name="process.memory.working_set.bytes",
                            value=float(mem_info.rss),
                            unit=MetricUnit.BYTES,
                            source="ProcessMemory",
                            target_id=f"PID:{self.target_pid}",
                            status="ok"
                        )
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied) as ex:
                records.append(
                    MetricObservation(
                        timestamp=now,
                        time_basis=TimeBasis.UTC_WALL_CLOCK,
                        metric_name="process.cpu.utilization.pct",
                        value=None,
                        unit=MetricUnit.PERCENT,
                        source="ProcessTimes",
                        target_id=f"PID:{self.target_pid}",
                        status="unavailable",
                        error_message=str(ex)
                    )
                )
                records.append(
                    MetricObservation(
                        timestamp=now,
                        time_basis=TimeBasis.UTC_WALL_CLOCK,
                        metric_name="process.memory.working_set.bytes",
                        value=None,
                        unit=MetricUnit.BYTES,
                        source="ProcessMemory",
                        target_id=f"PID:{self.target_pid}",
                        status="unavailable",
                        error_message=str(ex)
                    )
                )
        else:
            records.append(
                MetricObservation(
                    timestamp=now,
                    time_basis=TimeBasis.UTC_WALL_CLOCK,
                    metric_name="process.cpu.utilization.pct",
                    value=None,
                    unit=MetricUnit.PERCENT,
                    source="ProcessTimes",
                    target_id=f"PID:{self.target_pid}",
                    status="unavailable",
                    error_message=f"PID {self.target_pid} does not exist"
                )
            )

        # 4. Disk I/O throughput
        try:
            cur_disk = psutil.disk_io_counters()
            cur_time = time.time()
            if self._prev_disk_io and self._prev_disk_time:
                dt = cur_time - self._prev_disk_time
                if dt > 0:
                    read_rate = (cur_disk.read_bytes - self._prev_disk_io.read_bytes) / dt
                    write_rate = (cur_disk.write_bytes - self._prev_disk_io.write_bytes) / dt
                    records.append(
                        MetricObservation(
                            timestamp=now,
                            time_basis=TimeBasis.UTC_WALL_CLOCK,
                            metric_name="disk.io.read.bytes_per_sec",
                            value=max(0.0, read_rate),
                            unit=MetricUnit.BYTES_PER_SEC,
                            source="DiskCounters",
                            status="ok"
                        )
                    )
                    records.append(
                        MetricObservation(
                            timestamp=now,
                            time_basis=TimeBasis.UTC_WALL_CLOCK,
                            metric_name="disk.io.write.bytes_per_sec",
                            value=max(0.0, write_rate),
                            unit=MetricUnit.BYTES_PER_SEC,
                            source="DiskCounters",
                            status="ok"
                        )
                    )
            self._prev_disk_io = cur_disk
            self._prev_disk_time = cur_time
        except Exception as ex:
            records.append(
                MetricObservation(
                    timestamp=now,
                    time_basis=TimeBasis.UTC_WALL_CLOCK,
                    metric_name="disk.io.read.bytes_per_sec",
                    value=None,
                    unit=MetricUnit.BYTES_PER_SEC,
                    source="DiskCounters",
                    status="error",
                    error_message=str(ex)
                )
            )

        # 5. System Uptime
        try:
            boot_time = psutil.boot_time()
            uptime_sec = time.time() - boot_time
            records.append(
                MetricObservation(
                    timestamp=now,
                    time_basis=TimeBasis.UTC_WALL_CLOCK,
                    metric_name="system.uptime.seconds",
                    value=uptime_sec,
                    unit=MetricUnit.SECONDS,
                    source="GetTickCount64",
                    status="ok"
                )
            )
        except Exception as ex:
            records.append(
                MetricObservation(
                    timestamp=now,
                    time_basis=TimeBasis.UTC_WALL_CLOCK,
                    metric_name="system.uptime.seconds",
                    value=None,
                    unit=MetricUnit.SECONDS,
                    source="GetTickCount64",
                    status="error",
                    error_message=str(ex)
                )
            )

        # 6. Collector Health
        records.append(
            MetricObservation(
                timestamp=now,
                time_basis=TimeBasis.UTC_WALL_CLOCK,
                metric_name="collector.health.status",
                value=1.0,
                unit=MetricUnit.STATUS_FLAG,
                source="WinScope_Watchdog",
                status="ok"
            )
        )

        return records

    def run_session(
        self,
        duration_seconds: int = 5,
        output_file: Optional[str] = None
    ) -> SessionMetadata:
        """
        Executes a bounded collection session and persists records to JSONL.
        """
        session_id = str(uuid.uuid4())
        start_time = datetime.now(timezone.utc)
        metadata = SessionMetadata(
            session_id=session_id,
            start_time=start_time,
            host_name=socket.gethostname(),
            os_version=f"{platform.system()} {platform.release()} (Build {platform.version()})",
            sampling_interval_ms=self.sampling_interval_ms,
            collector_type="WinScope-CSharp-Native" if self.use_native_binary else "WinScope-Python-Collector",
            collector_version="1.0.0"
        )

        if output_file:
            os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)

        # If native binary execution requested:
        if self.use_native_binary:
            if not os.path.exists(self.native_binary_path):
                raise FileNotFoundError(f"Native collector binary not found at: {self.native_binary_path}")

            cmd = [
                self.native_binary_path,
                "--interval", str(self.sampling_interval_ms),
                "--duration", str(duration_seconds),
                "--pid", str(self.target_pid),
            ]
            if output_file:
                cmd.extend(["--output", output_file])

            proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
            metadata.end_time = datetime.now(timezone.utc)
            return metadata

        # Pure Python collection loop
        file_handle = open(output_file, "w", encoding="utf-8") if output_file else None
        try:
            if file_handle:
                header = metadata.model_dump(mode="json")
                header["type"] = "session_header"
                file_handle.write(json.dumps(header) + "\n")
                file_handle.flush()

            end_deadline = time.time() + duration_seconds
            interval_sec = self.sampling_interval_ms / 1000.0

            while time.time() < end_deadline:
                tick_start = time.time()
                obs_list = self.collect_single_snapshot()
                for obs in obs_list:
                    obs.validate_against_catalog()
                    if file_handle:
                        file_handle.write(obs.model_dump_json() + "\n")
                if file_handle:
                    file_handle.flush()

                elapsed = time.time() - tick_start
                sleep_rem = interval_sec - elapsed
                if sleep_rem > 0:
                    time.sleep(sleep_rem)
        finally:
            metadata.end_time = datetime.now(timezone.utc)
            if file_handle:
                footer = {
                    "type": "session_footer",
                    "session_id": session_id,
                    "end_time": metadata.end_time.isoformat(),
                    "collector_status": "completed"
                }
                file_handle.write(json.dumps(footer) + "\n")
                file_handle.close()

        return metadata
