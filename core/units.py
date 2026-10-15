"""
WinScope - Core Metric Definitions and Unit Specifications.

Defines the stable metric catalog, standard engineering units, and time bases.
"""

from enum import Enum
from typing import Dict, Any


class MetricUnit(str, Enum):
    PERCENT = "percent"
    BYTES = "bytes"
    BYTES_PER_SEC = "bytes/sec"
    SECONDS = "seconds"
    COUNT = "count"
    MILLISECONDS = "milliseconds"
    STATUS_FLAG = "status_flag"


class TimeBasis(str, Enum):
    UTC_WALL_CLOCK = "utc_wall_clock"       # System UTC time synchronized via NTP/W32Time
    HIGH_RES_PERF = "high_res_perf"         # High-resolution performance counter (QueryPerformanceCounter)
    SYSTEM_UPTIME = "system_uptime"         # Time elapsed since OS boot (GetTickCount64)


METRIC_CATALOG: Dict[str, Dict[str, Any]] = {
    "cpu.utilization.pct": {
        "unit": MetricUnit.PERCENT,
        "description": "Total processor utilization across all logical cores (0.0 to 100.0).",
        "source": "Win32_GetSystemTimes / PerfOS Processor Total",
        "valid_range": (0.0, 100.0),
    },
    "memory.physical.utilization.pct": {
        "unit": MetricUnit.PERCENT,
        "description": "Percentage of physical RAM in active use by the system and processes.",
        "source": "GlobalMemoryStatusEx (dwMemoryLoad)",
        "valid_range": (0.0, 100.0),
    },
    "memory.physical.available.bytes": {
        "unit": MetricUnit.BYTES,
        "description": "Available physical memory that can be immediately allocated without paging.",
        "source": "GlobalMemoryStatusEx (ullAvailPhys)",
        "valid_range": (0, None),
    },
    "memory.physical.total.bytes": {
        "unit": MetricUnit.BYTES,
        "description": "Total installed physical memory visible to the operating system.",
        "source": "GlobalMemoryStatusEx (ullTotalPhys)",
        "valid_range": (1, None),
    },
    "process.cpu.utilization.pct": {
        "unit": MetricUnit.PERCENT,
        "description": "Process-specific CPU utilization percentage normalized to available cores.",
        "source": "GetProcessTimes / Process performance counters",
        "valid_range": (0.0, 100.0),
    },
    "process.memory.working_set.bytes": {
        "unit": MetricUnit.BYTES,
        "description": "Physical memory pages currently resident in RAM for the target process.",
        "source": "K32GetProcessMemoryInfo (WorkingSetSize)",
        "valid_range": (0, None),
    },
    "disk.io.read.bytes_per_sec": {
        "unit": MetricUnit.BYTES_PER_SEC,
        "description": "Disk read throughput across monitored storage volumes.",
        "source": "LogicalDisk / PhysicalDisk performance counters",
        "valid_range": (0.0, None),
    },
    "disk.io.write.bytes_per_sec": {
        "unit": MetricUnit.BYTES_PER_SEC,
        "description": "Disk write throughput across monitored storage volumes.",
        "source": "LogicalDisk / PhysicalDisk performance counters",
        "valid_range": (0.0, None),
    },
    "system.uptime.seconds": {
        "unit": MetricUnit.SECONDS,
        "description": "Elapsed seconds since Windows kernel initialization.",
        "source": "GetTickCount64",
        "valid_range": (0.0, None),
    },
    "collector.health.status": {
        "unit": MetricUnit.STATUS_FLAG,
        "description": "Health status of the telemetry collector (1 = healthy, 0 = degraded/failing).",
        "source": "WinScope internal watchdog",
        "valid_range": (0, 1),
    },
}
