<div align="center">

# 🔭 WinScope
### Windows Telemetry & Performance Regression Lab

[![Platform](https://img.shields.io/badge/Platform-Windows%2011%20%7C%2010%20(x64)-0078D4?style=flat-square&logo=windows)](https://microsoft.com/windows)
[![C#](https://img.shields.io/badge/Collector-C%23%20%2F%20.NET%20Framework%204.8-512BD4?style=flat-square&logo=dotnet)](https://dotnet.microsoft.com)
[![Python](https://img.shields.io/badge/Analytics-Python%203.12-3776AB?style=flat-square&logo=python)](https://python.org)
[![Tests](https://img.shields.io/badge/Tests-23%20Passing%20(100%25)-34D399?style=flat-square&logo=pytest)](https://pytest.org)
[![Storage](https://img.shields.io/badge/Storage-SQLite%20WAL-003B57?style=flat-square&logo=sqlite)](https://sqlite.org)
[![Tracing](https://img.shields.io/badge/Diagnostics-ETW%20%7C%20WPA%20%7C%20WinDbg-FFB900?style=flat-square)](https://learn.microsoft.com/windows-hardware/drivers/debugger/)
[![License](https://img.shields.io/badge/License-MIT-gray?style=flat-square)](LICENSE)

<p align="center">
  A local-first Windows performance engineering and telemetry analytics platform.<br>
  Built to demonstrate systems instrumentation, data-quality pipelines, statistical regression testing, and post-mortem diagnostics modeled after <b>Microsoft Windows + Devices Fundamentals</b> engineering practices.
</p>

[Architecture](#-system-architecture) •
[Quickstart](#-quickstart) •
[Telemetry Catalog](#-metric-catalog--invariants) •
[Statistical Methodology](#-statistical-regression-engine) •
[Kernel Diagnostics](#-etw--windbg-diagnostics) •
[Verification](#-test-suite--verification)

---

</div>

## 🌟 Key Capabilities

- **⚡ Zero-Overhead Native Instrumentation:** High-performance C# collector communicating directly via Win32 P/Invoke (`GetSystemTimes`, `GlobalMemoryStatusEx`, `GetTickCount64`) with strict microsecond UTC timestamping.
- **🛡️ Resilient Streaming Ingestion Pipeline:** Schema contract enforcement, duplicate detection, inter-sample jitter analysis, and quarantine tables that isolate corrupted payloads without dropping stream continuity.
- **📊 Non-Parametric Anomaly & Regression Detection:** Differentiates ambient baseline jitter from confirmed functional regressions using Median Absolute Deviation (MAD), Modified Z-scores, Welch’s two-sample t-test, and 95% Confidence Intervals.
- **🧪 Bounded Experiment Orchestration:** Multi-phase controlled workload runner (pre-baseline $\to$ stimulus $\to$ recovery) for multi-core CPU arithmetic, memory page commitment, and scratch disk I/O.
- **🔬 Deep Windows Diagnostics:** Integrated Event Tracing for Windows (ETW) capture workflow via `wpr.exe` and a reproducible diagnostic target application triaged in **WinDbg** (`!analyze -v`, `.ecxr`, `~*kv`, `!syncblk`).
- **📈 Zero-Dependency Visualization:** Standalone interactive HTML/SVG telemetry dashboard and automated machine-readable JSON/Markdown diagnostic reports.

---

## 🏛️ System Architecture

```text
 ┌────────────────────────────────────────────────────────────────────────────────┐
 │                            TARGET WINDOWS PLATFORM                             │
 └───────┬──────────────────────────────────┬─────────────────────────────┬───────┘
         │                                  │                             │
 [Win32 P/Invoke API]             [wpr.exe ETW Tracing]         [Fault / Crash Target]
  • GetSystemTimes                 • GeneralProfile Session      • Access Violation (0xC0000005)
  • GlobalMemoryStatusEx           • Non-paged kernel buffers    • Thread Deadlock
  • GetTickCount64                 • .ETL trace generation       • WinDbg Triage (!analyze -v)
         │                                  │                             │
         ▼                                  ▼                             ▼
 ┌──────────────────────┐         ┌───────────────────┐         ┌───────────────────┐
 │ WinScope C# Native   │         │ Windows Perf      │         │ WinDbg Post-      │
 │ Collector Engine     │         │ Analyzer (WPA)    │         │ Mortem Analysis   │
 └──────────┬───────────┘         └───────────────────┘         └───────────────────┘
            │
            ▼ (RFC 8259 JSONL Stream)
 ┌────────────────────────────────────────────────────────────────────────────────┐
 │                      INGESTION & DATA QUALITY PIPELINE                         │
 │   • Schema Validation (Pydantic v2)           • Missing Interval Detection     │
 │   • Duplicate Observation Key Filter          • Corrupt Payload Quarantine     │
 └──────────┬─────────────────────────────────────────────────────────────────────┘
            │
            ▼
 ┌────────────────────────────────────────────────────────────────────────────────┐
 │                   DURABLE STORAGE LAYER (SQLite WAL MODE)                      │
 │   • sessions table        • observations (indexed on metric, timestamp)        │
 │   • quarantined_records   • data_quality_reports (sampling jitter & stats)     │
 └──────────┬─────────────────────────────────────────────────────────────────────┘
            │
            ▼
 ┌────────────────────────────────────────────────────────────────────────────────┐
 │                  STATISTICAL PERFORMANCE REGRESSION ENGINE                     │
 │   • Descriptive: Median (p50), MAD, p90, p99, Rolling Variance                 │
 │   • Anomaly Scoring: Boris Iglewicz & David Hoaglin Modified Z-Scores          │
 │   • Hypothesis Testing: Welch's Two-Sample t-Test & Mann-Whitney U             │
 │   • Uncertainty Bounds: 95% Confidence Intervals for Mean Difference           │
 └──────────┬─────────────────────────────────────────────────────────────────────┘
            │
            ├──────────────────────────────┬──────────────────────────────┐
            ▼                              ▼                              ▼
 ┌────────────────────┐         ┌────────────────────┐         ┌────────────────────┐
 │  Diagnostic Report │         │ Interactive HTML   │         │ SQL & KQL Query    │
 │  (JSON & Markdown) │         │ SVG Dashboard      │         │ Analytics Catalog  │
 └────────────────────┘         └────────────────────┘         └────────────────────┘
```

---

## 🚀 Quickstart

### Prerequisites
- **OS:** Windows 10 / 11 (x64)
- **Compilers:** Visual C# Roslyn Compiler (`csc.exe`) / .NET Framework 4.8
- **Runtimes:** Python 3.10+ (with `psutil`, `pywin32`, `pydantic`, `pytest`, `scipy`)

### 1. Clone & Build Native Collector
```powershell
git clone https://github.com/uday68/winscope.git
cd winscope

# Compile standalone native collector binary (WinScope.Collector.exe)
powershell -ExecutionPolicy Bypass -File .\collector\csharp\build.ps1
```

### 2. Run Automated Verification Test Suite
```powershell
python -m pytest tests/ -v
```

### 3. Execute End-to-End Experiment & Generate Reports
```powershell
# Runs an automated baseline vs. CPU stress workload experiment,
# validates telemetry, executes hypothesis testing, and renders reports
python scripts/run_experiment_demo.py
```
Outputs:
- 📊 **Interactive Dashboard:** `data/dashboard.html`
- 📑 **Executive Markdown Report:** `data/reports/real_regression_report.md`
- 💾 **Machine-Readable JSON:** `data/reports/real_regression_report.json`

---

## 📐 Metric Catalog & Invariants

WinScope defines atomic, strongly-typed telemetry contracts (`schema_version: "1.0.0"`).

| Canonical Metric | Unit | Native Source | Valid Range | Semantics |
| :--- | :--- | :--- | :--- | :--- |
| `cpu.utilization.pct` | `percent` | `Win32_GetSystemTimes` | $[0.0, 100.0]$ | Ratio of delta idle time to delta kernel+user time across all cores. |
| `memory.physical.utilization.pct` | `percent` | `GlobalMemoryStatusEx` | $[0.0, 100.0]$ | Physical RAM currently in active use (`dwMemoryLoad`). |
| `memory.physical.available.bytes` | `bytes` | `GlobalMemoryStatusEx` | $[0, \infty)$ | Physical memory immediately available without paging (`ullAvailPhys`). |
| `process.cpu.utilization.pct` | `percent` | `GetProcessTimes` | $[0.0, 100.0]$ | Monitored process CPU consumption normalized across processor count. |
| `process.memory.working_set.bytes`| `bytes` | `ProcessMemory` | $[0, \infty)$ | Resident physical memory pages currently allocated to process. |
| `system.uptime.seconds` | `seconds` | `GetTickCount64` | $[0, \infty)$ | Monotonic seconds elapsed since Windows kernel boot. |
| `collector.health.status` | `status_flag` | `WinScope_Watchdog` | $\{0, 1\}$ | Collector watchdog heartbeat ($1 = \text{healthy}, 0 = \text{degraded}$). |

> ### ⚠️ The Non-Zero Failure Invariant
> A core telemetry hygiene rule enforced by WinScope: **a collection failure or dead process is never silently converted into a `0.0` measurement.** Corrupted or unavailable counters preserve `value: null` with `status: "unavailable"` and explicit error descriptions. Converting failures to zero falsely skews percentiles and masks outages.

---

## 🔬 Statistical Regression Engine

Standard deviation and arithmetic means break down on skewed, heavy-tailed systems telemetry. WinScope uses robust non-parametric statistics and formal hypothesis testing:

### 1. Robust Standardized Scoring (Modified Z-Score)
To isolate true outliers from normal system burstiness without outlier distortion:
$$M_i = \frac{0.6745 \cdot (X_i - \tilde{X})}{\text{MAD}}$$
*where $\tilde{X}$ is the series median and $\text{MAD} = \text{median}(|X_i - \tilde{X}|)$.*
- **Transient Outlier:** Isolated sample with $|M_i| \ge 3.5$.
- **Sustained Deviation:** $\ge 3$ consecutive samples with $|M_i| \ge 3.0$.

### 2. Hypothesis Testing & Effect Size
- **Welch’s Two-Sample t-Test:** Evaluates unequal variances between baseline and candidate distributions.
- **95% Confidence Interval (Welch-Satterthwaite):** Calculates confidence interval for the mean shift $\Delta\mu$. If the confidence interval crosses zero or $p \ge 0.05$, the system refuses to claim causation and classifies the change as unverified noise.

```text
┌────────────────────────────────┬─────────────────┬──────────────────────────────┐
│ Experimental Condition         │ p-value         │ Automated Verdict            │
├────────────────────────────────┼─────────────────┼──────────────────────────────┤
│ Relative Shift ≥ +15%          │ p < 0.05        │ CONFIRMED_REGRESSION         │
│ Relative Shift ≤ -15%          │ p < 0.05        │ IMPROVEMENT                  │
│ Relative Shift ≥ +15%          │ p ≥ 0.05        │ POSSIBLE_REGRESSION_UNVERIFIED│
│ Within ±15% noise envelope     │ Any             │ NO_REGRESSION                │
│ Sample Size N < 3              │ Any             │ INCONCLUSIVE                 │
└────────────────────────────────┴─────────────────┴──────────────────────────────┘
```

---

## 🛠️ ETW & WinDbg Diagnostics

WinScope bridges the gap between high-level telemetry and deep operating system debugging:

### 1. Kernel Tracing with ETW
Capture low-overhead non-paged kernel buffers using native Windows Performance Recorder:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\capture_etw.ps1 -DurationSeconds 10
# Produces data/traces/WinScopeExperiment.etl -> Inspect in WPA (wpa.exe)
```
- **Context Switches & CPU Scheduling:** Precise thread state transitions (`ReadyThread` $\to$ `RunningThread`).
- **Disk I/O Latency:** Traces actual block-level read/write disk requests.

### 2. Post-Mortem Crash & Hang Triage
WinScope includes a dedicated diagnostic target binary (`diagnostics/CrashApp.cs`):
```powershell
powershell -ExecutionPolicy Bypass -File .\diagnostics\build_diagnostics.ps1
.\diagnostics\CrashApp.exe --crash     # Reproduces Access Violation (0xC0000005)
.\diagnostics\CrashApp.exe --deadlock  # Reproduces Inverted Lock Contention
```
In **WinDbg**:
- `!analyze -v`: Automated exception triage and bugcheck analysis.
- `.ecxr`: Switches processor register context directly to faulting instruction.
- `~*kv`: Dumps call stacks across all threads with parameter symbols.
- `!syncblk`: Detects circular wait chains and synchronization deadlocks.

Full documentation in [WINDBG_EXERCISE.md](diagnostics/WINDBG_EXERCISE.md).

---

## 🧪 Test Suite & Verification

The platform is backed by a deterministic test suite covering failure handling, mathematical invariants, and process lifecycles:

```powershell
python -m pytest tests/ -v
```

```text
============================= test session starts =============================
platform win32 -- Python 3.12.6, pytest-9.1.1 -- plugins: anyio, Faker, hydra-core
collected 23 items

tests/test_analysis.py::test_summary_statistics_deterministic PASSED     [  4%]
tests/test_analysis.py::test_robust_z_scores_and_anomaly_detection PASSED [  8%]
tests/test_analysis.py::test_regression_comparator_detects_shift PASSED  [ 13%]
tests/test_analysis.py::test_regression_comparator_insufficient_samples PASSED [ 17%]
tests/test_analysis.py::test_report_generation_json_and_markdown PASSED  [ 21%]
tests/test_collector.py::test_collector_single_snapshot PASSED           [ 26%]
tests/test_collector.py::test_collector_nonexistent_pid_failure_handling PASSED [ 30%]
tests/test_collector.py::test_collector_session_bounded_run PASSED       [ 34%]
tests/test_collector.py::test_csharp_native_binary_execution PASSED      [ 39%]
tests/test_experiments.py::test_cpu_stress_bounded_execution PASSED      [ 43%]
tests/test_experiments.py::test_memory_workload_safe_allocation_and_release PASSED [ 47%]
tests/test_experiments.py::test_disk_io_workload_cleanup PASSED          [ 52%]
tests/test_experiments.py::test_workload_cancellation PASSED             [ 56%]
tests/test_experiments.py::test_experiment_runner_multiphase_run PASSED  [ 60%]
tests/test_ingestion.py::test_ingestion_valid_stream PASSED              [ 65%]
tests/test_ingestion.py::test_ingestion_quarantines_malformed_and_duplicate PASSED [ 69%]
tests/test_ingestion.py::test_ingestion_detects_missing_interval PASSED  [ 73%]
tests/test_models.py::test_metric_observation_valid PASSED               [ 78%]
tests/test_models.py::test_metric_observation_unit_mismatch PASSED       [ 82%]
tests/test_models.py::test_metric_observation_range_violation PASSED     [ 86%]
tests/test_models.py::test_metric_observation_failure_never_emits_synthetic_zero PASSED [ 91%]
tests/test_models.py::test_invalid_status_rejection PASSED               [ 95%]
tests/test_models.py::test_session_metadata_validation PASSED            [100%]

============================= 23 passed in 15.51s =============================
```

---

## 📂 Project Organization

```text
winscope/
├── collector/          # Native C# (P/Invoke) & Python system telemetry collectors
├── core/               # Pydantic v2 telemetry schemas, metric catalog & time bases
├── storage/            # SQLite connection manager, WAL mode, migrations & indexes
├── ingestion/          # Streaming parser, deduplication, quarantine & jitter metrics
├── workloads/          # Bounded synthetic workloads (CPU, memory, disk, idle)
├── analysis/           # MAD, robust Z-scores, Welch's t-test, regression engine
├── diagnostics/        # ETW capture scripts, CrashApp fault target & WinDbg lab
├── analytics/          # Production SQL & Kusto Query Language (KQL) catalogs
├── visualization/      # Offline responsive HTML/SVG telemetry dashboard
├── scripts/            # PowerShell runners & automated experiment demos
└── tests/              # 23 automated unit and integration tests
```

---

## 📜 License

Licensed under the [MIT License](LICENSE). Built for educational and systems performance engineering demonstrations.
