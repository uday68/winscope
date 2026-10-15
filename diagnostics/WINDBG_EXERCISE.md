# Windows Diagnostic Workflow: ETW, WPA, and WinDbg

This diagnostic exercise bridges high-level performance telemetry with kernel-level Event Tracing for Windows (ETW) and post-mortem crash/hang debugging in WinDbg.

---

## 1. Event Tracing for Windows (ETW) & WPA Analysis

### ETW Architecture Overview
Event Tracing for Windows is a kernel-level tracing facility providing low-overhead event logging:
- **Providers:** Windows kernel components, device drivers, or user-mode applications that emit structured events.
- **Controllers / Sessions:** Start/stop sessions and route buffers (e.g. `wpr.exe` or `logman.exe`).
- **Buffers:** Non-paged kernel pool memory buffers written locklessly per logical processor.
- **Consumers:** Analytical parsers and visualizers (`wpa.exe` or TraceEvent library).

### Capture Workflow
Capture an ETW trace during a WinScope controlled experiment:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\capture_etw.ps1 -DurationSeconds 10
```
This produces `data\traces\WinScopeExperiment.etl`.

### Inspecting in Windows Performance Analyzer (WPA)
1. Launch WPA: `wpa.exe data\traces\WinScopeExperiment.etl`
2. **CPU Utilization (Sampled):**
   - Graph: *Computation -> CPU Usage (Sampled)*
   - Grouping: `Process`, `Thread ID`, `Stack`
   - Look for high sample density in `WinScope.Collector.exe` or worker processes.
3. **Context Switching & Scheduling:**
   - Graph: *Computation -> CPU Usage (Precise)*
   - Analyzes thread transitions (`ReadyThread` -> `RunningThread`), wait reasons, and context switch latencies.
4. **Disk I/O Activity:**
   - Graph: *Storage -> Disk I/O*
   - Grouping: `Process`, `Priority`, `Path Name`
   - Verify that disk activity correlates precisely with the time intervals recorded by WinScope.

---

## 2. Post-Mortem Crash Triage with WinDbg

WinScope includes a diagnostic target binary: `diagnostics\CrashApp.exe`.

### Scenario A: Access Violation / Crash Triage

1. **Launch under WinDbg:**
   ```cmd
   windbgx.exe diagnostics\CrashApp.exe --crash
   ```
   Or capture a minidump using ProcDump:
   ```cmd
   procdump.exe -e -ma -x data\dumps diagnostics\CrashApp.exe --crash
   ```

2. **WinDbg Analysis Commands:**
   ```text
   0:000> !analyze -v
   ```
   *Output Highlights:*
   - `FAULTING_IP`: Identifies the exact instruction that dereferenced a null pointer (e.g. `mov eax, [rcx]`).
   - `EXCEPTION_CODE`: `(NTSTATUS) 0xc0000005 - The instruction at 0x... referenced memory at 0x0000000000000000. The memory could not be read.`
   - `BUGCHECK_STR`: `APPLICATION_FAULT_NULL_CLASS_PTR_DEREFERENCE`

3. **Switch to Exception Context:**
   ```text
   0:000> .ecxr
   0:000> kL
   ```
   *Call Stack Analysis:*
   ```text
   # Child-SP          RetAddr               Call Site
   00 0000003b`f71fe960 00007ffb`428f1105     CrashApp!WinScope.Diagnostics.CrashApp.TriggerAccessViolation()
   01 0000003b`f71fe9a0 00007ffb`428f1042     CrashApp!WinScope.Diagnostics.CrashApp.Main(System.String[] args)
   ```

---

## 3. Scenario B: Thread Deadlock / Synchronization Hang Triage

1. **Launch Deadlock App:**
   ```cmd
   diagnostics\CrashApp.exe --deadlock
   ```
   *Process output:*
   - `[Thread 1] Acquired Lock A, waiting for Lock B...`
   - `[Thread 2] Acquired Lock B, waiting for Lock A...`

2. **Attach WinDbg or generate hang dump:**
   ```cmd
   procdump.exe -h -ma CrashApp.exe data\dumps\deadlock.dmp
   ```

3. **WinDbg Deadlock Inspection:**
   ```text
   0:000> ~*kv
   ```
   *Displays all thread call stacks.*

   - **Inspect Thread 1:**
     Blocked inside `Monitor.Enter(LockB)` waiting on critical section held by Thread 2.
   - **Inspect Thread 2:**
     Blocked inside `Monitor.Enter(LockA)` waiting on critical section held by Thread 1.

4. **Verify Contention with SOS / CLR Extension:**
   ```text
   0:000> .loadby sos clr
   0:000> !syncblk
   ```
   *Output shows circular wait chain:*
   - Monitor object `LockA` owned by Thread 1, requested by Thread 2.
   - Monitor object `LockB` owned by Thread 2, requested by Thread 1.

---

## 4. Evidence vs. Uncertainty Analysis

| Observed Evidence (What the Dump Proves) | Open Uncertainty (What Requires Further Investigation) |
| :--- | :--- |
| Thread 1 and Thread 2 are in a mutual wait cycle holding `LockA` and `LockB`. | Did a prior exception in a third thread fail to release an earlier lock? |
| Register `rcx` was `0x00000000` at the point of the Access Violation. | Which business logic or input parsing path allowed the pointer to become null? |
| Exact wall-clock timestamp when faulting instruction was dispatched. | Did preceding memory pressure or heap fragmentation contribute to state corruption? |
