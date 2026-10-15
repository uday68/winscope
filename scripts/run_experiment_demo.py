"""
WinScope - End-to-End Performance Experiment Demo.

Executes:
1. Baseline measurement run (Idle)
2. Candidate measurement run (Controlled CPU Stress)
3. Database ingestion & data quality verification
4. Statistical regression analysis & report generation
"""

import os
import sys
import json

# Ensure project root is in python search path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from workloads.scenarios import IdleBaselineWorkload, CpuStressWorkload
from workloads.runner import PerformanceExperimentRunner
from storage.db import TelemetryDatabase
from analysis.regression import PerformanceRegressionComparator
from analysis.report import DiagnosticReportGenerator
from visualization.dashboard import WinScopeDashboard


def main():
    os.makedirs("data/reports", exist_ok=True)
    db = TelemetryDatabase()
    runner = PerformanceExperimentRunner(db=db)

    print("==========================================================")
    print(" WinScope End-to-End Performance Regression Lab")
    print("==========================================================")

    # 1. Baseline Experiment (Idle)
    print("\n[Stage 1/4] Running Baseline Experiment (Idle System)...")
    base_res = runner.run_experiment(
        workload=IdleBaselineWorkload(duration_sec=3),
        pre_baseline_sec=1,
        post_recovery_sec=1,
        sampling_interval_ms=1000,
        is_baseline=True
    )
    base_sid = base_res["quality_report"].session_id
    print(f" -> Baseline completed. Session: {base_sid}")
    print(f" -> Records accepted: {base_res['quality_report'].accepted_records}")

    # 2. Candidate Experiment (CPU Stress)
    print("\n[Stage 2/4] Running Candidate Experiment (Controlled Multi-core CPU Stress)...")
    cand_res = runner.run_experiment(
        workload=CpuStressWorkload(duration_sec=3, thread_count=2, intensity=1.0),
        pre_baseline_sec=1,
        post_recovery_sec=1,
        sampling_interval_ms=1000,
        is_baseline=False
    )
    cand_sid = cand_res["quality_report"].session_id
    print(f" -> Candidate completed. Session: {cand_sid}")
    print(f" -> Records accepted: {cand_res['quality_report'].accepted_records}")

    # 3. Statistical Comparison
    print("\n[Stage 3/4] Querying SQLite and executing hypothesis testing...")
    with db.connection() as conn:
        base_cpu = [
            r["value"] for r in conn.execute(
                "SELECT value FROM observations WHERE session_id = ? AND metric_name = 'cpu.utilization.pct' AND status = 'ok'",
                (base_sid,)
            ).fetchall()
        ]
        cand_cpu = [
            r["value"] for r in conn.execute(
                "SELECT value FROM observations WHERE session_id = ? AND metric_name = 'cpu.utilization.pct' AND status = 'ok'",
                (cand_sid,)
            ).fetchall()
        ]
        base_mem = [
            r["value"] for r in conn.execute(
                "SELECT value FROM observations WHERE session_id = ? AND metric_name = 'memory.physical.utilization.pct' AND status = 'ok'",
                (base_sid,)
            ).fetchall()
        ]
        cand_mem = [
            r["value"] for r in conn.execute(
                "SELECT value FROM observations WHERE session_id = ? AND metric_name = 'memory.physical.utilization.pct' AND status = 'ok'",
                (cand_sid,)
            ).fetchall()
        ]

    comp_cpu = PerformanceRegressionComparator.compare_metrics(
        baseline_series=base_cpu,
        candidate_series=cand_cpu,
        metric_name="cpu.utilization.pct",
        unit="percent",
        regression_threshold_pct=15.0
    )

    comp_mem = PerformanceRegressionComparator.compare_metrics(
        baseline_series=base_mem,
        candidate_series=cand_mem,
        metric_name="memory.physical.utilization.pct",
        unit="percent",
        regression_threshold_pct=10.0
    )

    print(f" -> CPU Comparison: {comp_cpu['verdict']} (Shift: {comp_cpu.get('relative_diff_median_pct'):+.1f}%, p-value: {comp_cpu.get('ttest_pvalue')})")
    print(f" -> Memory Comparison: {comp_mem['verdict']} (Shift: {comp_mem.get('relative_diff_median_pct'):+.1f}%)")

    # 4. Generate Reports & Dashboard
    print("\n[Stage 4/4] Generating Diagnostic Reports and Interactive Dashboard...")
    report_data = DiagnosticReportGenerator.generate_json_report(
        baseline_session_id=base_sid,
        candidate_session_id=cand_sid,
        comparisons=[comp_cpu, comp_mem],
        limitations=[
            "Host runs background OS processes; ambient activity contributes minor baseline noise.",
            "Workload execution is strictly bounded to prevent host instability."
        ]
    )

    json_path = "data/reports/real_regression_report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)

    md_path = "data/reports/real_regression_report.md"
    md_report = DiagnosticReportGenerator.generate_markdown_report(report_data)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_report)

    dashboard = WinScopeDashboard(db=db)
    dash_path = dashboard.generate_html_dashboard(session_id=cand_sid, output_html_path="data/dashboard.html")

    print(f" -> JSON Report:      {os.path.abspath(json_path)}")
    print(f" -> Markdown Report:  {os.path.abspath(md_path)}")
    print(f" -> HTML Dashboard:   {dash_path}")
    print("\nExperiment run completed successfully!")


if __name__ == "__main__":
    main()
