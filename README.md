# WinScope — Windows Telemetry & Performance Regression Lab

WinScope is a local-first Windows performance engineering and telemetry analytics platform built to demonstrate systems fundamentals relevant to the **Microsoft Windows + Devices Fundamentals Software Engineering** role.

The platform collects and imports real Windows diagnostic data, validates schemas, persists observations in SQLite, executes controlled workloads, detects anomalies using robust statistics, produces regression reports, and provides an end-to-end ETW/WPA and WinDbg diagnostic workflow.

---

## 1. System Architecture & Components

```text
d:\windoze\
├── collector\
│   ├── csharp\
│   │   ├── Program.cs                  # High-performance native Win32/C# telemetry collector (P/Invoke)
│   │   ├── build.ps1                   # Roslyn compiler build script (VS/Framework csc)
│   │   └── bin\WinScope.Collector.exe  # Compiled native collector executable
│   └── python\
│       ├── __init__.py
│       └── collector.py                # Python collector engine (psutil/pywin32) & C# orchestrator
├── core\
│   ├── __init__.py
│   ├── units.py                        # Metric catalog, engineering units, and time bases
│   └── models.py                       # Strict Pydantic v2 schemas for telemetry & sessions
├── storage\
│   ├── __init__.py
│   └── db.py                           # SQLite connection manager, WAL mode, schema migrations & indexes
├── ingestion\
│   ├── __init__.py
│   ├── quality.py                      # Data quality report models & interval distribution analysis
│   └── pipeline.py                     # Streaming parser, deduplication, quarantine, and SQLite bulk ingest
├── workloads\
│   ├── __init__.py
│   ├── scenarios.py                    # Controlled workloads (CPU stress, memory pressure, disk I/O, idle)
│   └── runner.py                       # Multi-phase experiment coordinator (pre-baseline -> workload -> recovery)
├── analysis\
│   ├── __init__.py
│   ├── engine.py                       # Rolling stats, MAD, robust Modified Z-scores, anomaly detection
│   ├── regression.py                   # Welch's t-test, Mann-Whitney U, 95% CIs, regression classification
│   └── report.py                       # Machine-readable JSON and human-readable Markdown/HTML reports
├── diagnostics\
│   ├── CrashApp.cs                     # Controlled faulty test binary (NullReference AV & thread deadlock)
│   ├── build_diagnostics.ps1           # Roslyn build script for CrashApp.exe
│   ├── CrashApp.exe                    # Compiled target application with debug symbols
│   └── WINDBG_EXERCISE.md              # Full WinDbg triage and WPA trace analysis workflow
├── analytics\
│   ├── queries.sql                     # Production SQL queries for SQLite (rolling averages, missing intervals)
│   └── queries.kql                     # KQL queries for Azure Monitor / Kusto / ADX
├── visualization\
│   └── dashboard.py                    # Zero-dependency responsive HTML/SVG telemetry dashboard
├── scripts\
│   ├── run_collection.ps1              # Single-session collection script (C# or Python)
│   ├── capture_etw.ps1                 # Native Event Tracing for Windows capture script via wpr.exe
│   └── run_experiment_demo.py          # End-to-end baseline vs candidate regression runner
├── tests\
│   ├── test_models.py                  # Schema, units, and missing-value invariant tests
│   ├── test_collector.py               # Live snapshot, bounded run, and native C# execution tests
│   ├── test_ingestion.py               # Ingestion, deduplication, quarantine, and gap detection tests
│   ├── test_experiments.py             # Workload limits, cancellation, and multi-phase execution tests
│   └── test_analysis.py                # Statistical moments, robust z-scores, hypothesis tests, and reports
├── data\
│   ├── raw\                            # Real captured Windows telemetry sessions (.jsonl)
│   ├── fixtures\                       # Deterministic synthetic test fixtures (.jsonl)
│   ├── reports\                        # Real generated regression reports (.json, .md)
│   ├── dashboard.html                  # Standalone interactive performance dashboard
│   └── winscope.db                     # Durable SQLite telemetry store
└── README.md
```

---

## 2. Minimum Prerequisites & Tooling Verification

| Prerequisite | Installed Version on Machine | Purpose / Role |
| :--- | :--- | :--- |
| **Operating System** | Windows 11 Build 26100 (x64) | Target platform under observation |
| **PowerShell** | 5.1 (Build 26100) | Automation and experiment orchestration |
| **C# Compiler (Roslyn)** | Visual C# Compiler 3.11.0 / .NET Framework 4.8 | Native, zero-overhead telemetry binary compilation |
| **Python** | 3.12.6 (`psutil`, `pywin32`, `pydantic`, `pytest`, `scipy`) | Telemetry parsing, validation, statistics, and testing |
| **Windows Diagnostic Tools** | `wpr.exe` (10.0.26100), `typeperf.exe` | Native ETW recording and counter probing |

---

## 3. How to Run & Verify

### 1. Run the Complete Automated Test Suite (23 Tests)
```powershell
python -m pytest tests/ -v
```

### 2. Run the End-to-End Performance Regression Experiment
```powershell
python scripts/run_experiment_demo.py
```
This executes:
1. Baseline measurement run (Idle system).
2. Candidate measurement run (Controlled multi-core CPU stress).
3. Streaming ingestion into SQLite with deduplication and quality reporting.
4. Comparative hypothesis testing (Welch's t-test, Mann-Whitney U, 95% CI).
5. Emits `data/reports/real_regression_report.json`, `data/reports/real_regression_report.md`, and `data/dashboard.html`.

### 3. Build & Test Diagnostic Fault Application (WinDbg Triage)
```powershell
powershell -ExecutionPolicy Bypass -File .\diagnostics\build_diagnostics.ps1
.\diagnostics\CrashApp.exe --crash
.\diagnostics\CrashApp.exe --deadlock
```
See [WINDBG_EXERCISE.md](file:///d:/windoze/diagnostics/WINDBG_EXERCISE.md) for step-by-step WinDbg command analysis (`!analyze -v`, `.ecxr`, `~*kv`, `!syncblk`).

### 4. Capture Real ETW Traces with Windows Performance Recorder
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\capture_etw.ps1 -DurationSeconds 10
```
Produces `data/traces/WinScopeExperiment.etl` ready to open in Windows Performance Analyzer (`wpa.exe`).

---

## 4. Engineering Principles & Invariants

1. **Failure Invariant:** WinScope never converts collection failures or terminated processes into a silent `0.0`. Missing or unreadable metrics preserve `value: null` with `status: "unavailable"` and explicit error descriptions.
2. **Correlation vs. Causation:** Regression reports distinguish statistically supported shifts ($p < 0.05$) from unverified trends and separate measured shifts from inferred explanations.
3. **Safety & Containment:** Synthetic workloads are strictly bounded in thread count, duty cycle, memory allocation, and scratch directory scope.
