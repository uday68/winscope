"""
WinScope - Controlled Workload Scenarios.

Implements bounded, safe synthetic workloads designed to generate repeatable
performance signals without causing system instability or unconstrained resource exhaustion.
"""

import os
import time
import math
import tempfile
import threading
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class BaseWorkload(ABC):
    """Abstract base class for all WinScope workloads."""

    def __init__(self, name: str, duration_sec: int = 5):
        self.name = name
        self.duration_sec = max(1, duration_sec)
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    @abstractmethod
    def execute(self) -> Dict[str, Any]:
        """Runs the workload within safe bounds and returns run metadata."""
        pass


class IdleBaselineWorkload(BaseWorkload):
    """
    Idle baseline workload. Performs no synthetic work to capture ambient system state.
    """

    def __init__(self, duration_sec: int = 5):
        super().__init__("idle_baseline", duration_sec)

    def execute(self) -> Dict[str, Any]:
        start = time.time()
        while time.time() - start < self.duration_sec and not self._stop_event.is_set():
            time.sleep(0.1)
        return {
            "workload": self.name,
            "actual_duration_sec": time.time() - start,
            "target_duration_sec": self.duration_sec,
        }


class CpuStressWorkload(BaseWorkload):
    """
    Controlled CPU workload. Performs bound mathematical operations across specified threads.
    """

    def __init__(self, duration_sec: int = 5, thread_count: int = 2, intensity: float = 1.0):
        super().__init__("cpu_stress", duration_sec)
        self.thread_count = min(max(1, thread_count), os.cpu_count() or 2)
        self.intensity = min(max(0.1, intensity), 1.0)

    def _worker(self, deadline: float):
        ops = 0
        while time.time() < deadline and not self._stop_event.is_set():
            # Perform bounded trigonometric and prime-checking operations
            for _ in range(5000):
                math.sin(ops) * math.cos(ops)
                ops += 1
            if self.intensity < 1.0:
                time.sleep((1.0 - self.intensity) * 0.01)

    def execute(self) -> Dict[str, Any]:
        start = time.time()
        deadline = start + self.duration_sec
        threads = [
            threading.Thread(target=self._worker, args=(deadline,), daemon=True)
            for _ in range(self.thread_count)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        return {
            "workload": self.name,
            "actual_duration_sec": time.time() - start,
            "thread_count": self.thread_count,
            "intensity": self.intensity,
        }


class MemoryAllocationWorkload(BaseWorkload):
    """
    Controlled memory allocation workload.
    Allocates a bounded chunk of RAM (e.g. 100MB), writes to pages to commit them,
    holds for duration, and cleanly releases.
    """

    def __init__(self, duration_sec: int = 5, target_mb: int = 128):
        super().__init__("memory_pressure", duration_sec)
        # Safe bound: limit synthetic allocation between 16MB and 512MB
        self.target_mb = min(max(16, target_mb), 512)

    def execute(self) -> Dict[str, Any]:
        start = time.time()
        allocated_chunks = []
        chunk_size = 1024 * 1024  # 1 MB

        try:
            # Allocate and commit memory pages
            for _ in range(self.target_mb):
                if self._stop_event.is_set():
                    break
                # Writing non-zero bytes forces physical commitment of pages (working set)
                chunk = bytearray(b"\xAA" * chunk_size)
                allocated_chunks.append(chunk)

            # Hold memory for the requested duration
            while time.time() - start < self.duration_sec and not self._stop_event.is_set():
                time.sleep(0.1)

        finally:
            # Explicitly deallocate
            del allocated_chunks

        return {
            "workload": self.name,
            "actual_duration_sec": time.time() - start,
            "allocated_mb": self.target_mb,
        }


class DiskIoWorkload(BaseWorkload):
    """
    Controlled disk I/O workload.
    Writes and reads sequential blocks in a safe local scratch directory,
    then automatically deletes all temporary files.
    """

    def __init__(self, duration_sec: int = 5, block_size_kb: int = 64, target_mb: int = 50):
        super().__init__("disk_io", duration_sec)
        self.block_size = min(max(4, block_size_kb), 1024) * 1024
        self.target_mb = min(max(5, target_mb), 200)

    def execute(self) -> Dict[str, Any]:
        start = time.time()
        total_bytes_written = 0
        total_bytes_read = 0

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "winscope_io_test.dat")
            block = os.urandom(self.block_size)
            blocks_to_write = (self.target_mb * 1024 * 1024) // self.block_size

            # Write phase
            with open(test_file, "wb") as f:
                for _ in range(blocks_to_write):
                    if self._stop_event.is_set() or (time.time() - start) >= self.duration_sec:
                        break
                    f.write(block)
                    total_bytes_written += len(block)
                f.flush()
                os.fsync(f.fileno())

            # Read phase
            if os.path.exists(test_file) and not self._stop_event.is_set():
                with open(test_file, "rb") as f:
                    while time.time() - start < self.duration_sec and not self._stop_event.is_set():
                        data = f.read(self.block_size)
                        if not data:
                            f.seek(0)
                            continue
                        total_bytes_read += len(data)

        return {
            "workload": self.name,
            "actual_duration_sec": time.time() - start,
            "bytes_written": total_bytes_written,
            "bytes_read": total_bytes_read,
        }
