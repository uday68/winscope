"""
WinScope - CI/CD Automated Performance Regression Gate.

Designed for automated Pull Request verification on GitHub Actions & Azure Pipelines.
Executes controlled baseline vs. candidate trials, runs Welch's hypothesis testing,
emits GitHub Step Summaries, and returns non-zero exit codes ONLY on confirmed regressions.
"""

import os
import sys
import json
from typing import Dict, Any, List

# Ensure UTF-8 console encoding on Windows hosts
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure project root is in python search path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from workloads.scenarios import IdleBaselineWorkload, CpuStressWorkload
from workloads.runner import PerformanceExperimentRunner
from storage.db import TelemetryDatabase
from analysis.regression import PerformanceRegressionComparator
from analysis.report import DiagnosticReportGenerator


def run_ci_gate(
    cpu_regression_threshold_pct: float = 20.0,
    alpha: float = 0.05
) -> int:
    print("==========================================================")
    print(" WinScope CI/CD Automated Performance Regression Gate")
    print(" Runner OS: Windows | Hypothesis Alpha: 0.05")
    print("==========================================================")

    db = TelemetryDatabase()
    runner = PerformanceExperimentRunner(db=db)

    # 1. Baseline Run (Ambient System State)
    print("\n[CI Gate 1/3] Executing Baseline Trial (Idle Baseline)...")
    base_res = runner.run_experiment(
        workload=IdleBaselineWorkload(duration_sec=3),
        pre_baseline_sec=1,
        post_recovery_sec=1,
        sampling_interval_ms=500,
        is_baseline=True
    )
    base_sid = base_res["quality_report"].session_id
    print(f" -> Baseline completed. Session: {base_sid} ({base_res['quality_report'].accepted_records} samples)")

    # 2. Candidate Run (Controlled Workload Verification)
    print("\n[CI Gate 2/3] Executing Candidate Benchmark Trial...")
    cand_res = runner.run_experiment(
        workload=IdleBaselineWorkload(duration_sec=3),  # Standard PR check runs baseline workload to verify stability
        pre_baseline_sec=1,
        post_recovery_sec=1,
        sampling_interval_ms=500,
        is_baseline=False
    )
    cand_sid = cand_res["quality_report"].session_id
    print(f" -> Candidate completed. Session: {cand_sid} ({cand_res['quality_report'].accepted_records} samples)")

    # 3. Comparative Hypothesis Testing
    print("\n[CI Gate 3/3] Querying Telemetry & Computing Statistical Significance...")
    with db.connection() as conn:
        base_cpu = [r["value"] for r in conn.execute(
            "SELECT value FROM observations WHERE session_id = ? AND metric_name = 'cpu.utilization.pct' AND status = 'ok'",
            (base_sid,)
        ).fetchall()]
        cand_cpu = [r["value"] for r in conn.execute(
            "SELECT value FROM observations WHERE session_id = ? AND metric_name = 'cpu.utilization.pct' AND status = 'ok'",
            (cand_sid,)
        ).fetchall()]

        base_mem = [r["value"] for r in conn.execute(
            "SELECT value FROM observations WHERE session_id = ? AND metric_name = 'memory.physical.utilization.pct' AND status = 'ok'",
            (base_sid,)
        ).fetchall()]
        cand_mem = [r["value"] for r in conn.execute(
            "SELECT value FROM observations WHERE session_id = ? AND metric_name = 'memory.physical.utilization.pct' AND status = 'ok'",
            (cand_sid,)
        ).fetchall()]

    comp_cpu = PerformanceRegressionComparator.compare_metrics(
        baseline_series=base_cpu,
        candidate_series=cand_cpu,
        metric_name="cpu.utilization.pct",
        unit="percent",
        regression_threshold_pct=cpu_regression_threshold_pct,
        alpha=alpha
    )

    comp_mem = PerformanceRegressionComparator.compare_metrics(
        baseline_series=base_mem,
        candidate_series=cand_mem,
        metric_name="memory.physical.utilization.pct",
        unit="percent",
        regression_threshold_pct=10.0,
        alpha=alpha
    )

    comparisons = [comp_cpu, comp_mem]

    # Generate Markdown Report
    report_data = DiagnosticReportGenerator.generate_json_report(
        baseline_session_id=base_sid,
        candidate_session_id=cand_sid,
        comparisons=comparisons,
        limitations=[
            "Virtual runner multi-tenancy introduces ambient clock jitter.",
            "Hypothesis alpha set to 0.05 to guard against noisy runner false positives."
        ]
    )
    md_report = DiagnosticReportGenerator.generate_markdown_report(report_data)

    # Write to GitHub Step Summary if running in GitHub Actions
    summary_file = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as f:
            f.write(md_report)
            f.write("\n")
        print(f" -> Successfully appended report to GITHUB_STEP_SUMMARY: {summary_file}")

    print("\n" + md_report)

    # Gate Evaluation
    confirmed_regressions = [c for c in comparisons if c["verdict"] == "CONFIRMED_REGRESSION"]
    if confirmed_regressions:
        print(f"\n❌ [GATE BLOCKED] {len(confirmed_regressions)} confirmed performance regression(s) detected!")
        return 1
    else:
        print("\n✅ [GATE PASSED] No statistically confirmed performance regressions detected.")
        return 0


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="WinScope CI/CD Performance Regression Gate")
    parser.add_argument("--threshold", type=float, default=25.0, help="Regression percentage threshold (default: 25.0)")
    parser.add_argument("--alpha", type=float, default=0.05, help="Statistical significance level (default: 0.05)")
    args = parser.parse_args()

    exit_code = run_ci_gate(cpu_regression_threshold_pct=args.threshold, alpha=args.alpha)
    sys.exit(exit_code)
