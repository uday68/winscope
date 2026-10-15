"""
Unit tests for StatisticalAnalysisEngine, PerformanceRegressionComparator, and DiagnosticReportGenerator.
"""

import pytest
import numpy as np
from analysis.engine import StatisticalAnalysisEngine
from analysis.regression import PerformanceRegressionComparator
from analysis.report import DiagnosticReportGenerator


def test_summary_statistics_deterministic():
    series = [10.0, 10.0, 10.0, 10.0, 10.0]
    stats = StatisticalAnalysisEngine.compute_summary_statistics(series)
    assert stats["count"] == 5
    assert stats["mean"] == 10.0
    assert stats["median"] == 10.0
    assert stats["mad"] == 0.0
    assert stats["is_zero_variance"] is True


def test_robust_z_scores_and_anomaly_detection():
    # 10 baseline samples around 20, 1 isolated outlier (100.0), 4 sustained samples around 80.0
    series = [20.0, 20.1, 19.9, 20.2, 100.0, 20.0, 19.8, 80.0, 81.0, 79.5, 80.5]
    timestamps = [f"2026-10-15T12:00:{i:02d}Z" for i in range(len(series))]

    anomalies = StatisticalAnalysisEngine.detect_anomalies(
        series, timestamps, z_threshold=3.0, sustained_window=3
    )

    # Must distinguish between the isolated outlier at idx 4 and the sustained shift
    assert len(anomalies["transient_outliers"]) >= 1
    assert anomalies["transient_outliers"][0]["value"] == 100.0
    assert len(anomalies["sustained_deviations"]) >= 1
    assert anomalies["sustained_deviations"][0]["samples"] >= 3


def test_regression_comparator_detects_shift():
    # Baseline: mean 20, Candidate: mean 50
    np.random.seed(42)
    baseline = list(np.random.normal(loc=20.0, scale=1.0, size=20))
    candidate = list(np.random.normal(loc=50.0, scale=1.0, size=20))

    comp = PerformanceRegressionComparator.compare_metrics(
        baseline_series=baseline,
        candidate_series=candidate,
        metric_name="cpu.utilization.pct",
        unit="percent",
        regression_threshold_pct=15.0
    )

    assert comp["verdict"] == "CONFIRMED_REGRESSION"
    assert comp["ttest_pvalue"] < 0.001
    assert comp["relative_diff_median_pct"] > 50.0
    assert comp["ci_95"] is not None


def test_regression_comparator_insufficient_samples():
    comp = PerformanceRegressionComparator.compare_metrics(
        baseline_series=[10.0, 12.0],
        candidate_series=[15.0],
        metric_name="cpu.utilization.pct",
        unit="percent"
    )
    assert comp["verdict"] == "INCONCLUSIVE"


def test_report_generation_json_and_markdown():
    comparisons = [{
        "metric_name": "cpu.utilization.pct",
        "unit": "percent",
        "verdict": "CONFIRMED_REGRESSION",
        "explanation": "Statistically supported increase",
        "absolute_diff_median": 25.0,
        "relative_diff_median_pct": 125.0,
        "ttest_pvalue": 0.0001,
        "ci_95": (23.5, 26.5),
        "baseline_stats": {"count": 10, "median": 20.0, "mad": 0.5, "p90": 21.0, "p99": 21.5},
        "candidate_stats": {"count": 10, "median": 45.0, "mad": 0.8, "p90": 46.0, "p99": 46.5},
    }]

    rep_json = DiagnosticReportGenerator.generate_json_report(
        baseline_session_id="base-123",
        candidate_session_id="cand-456",
        comparisons=comparisons,
        limitations=["Ambient background CPU activity may contribute jitter."]
    )
    assert rep_json["baseline_session_id"] == "base-123"

    md = DiagnosticReportGenerator.generate_markdown_report(rep_json)
    assert "# WinScope — Performance Regression Diagnostic Report" in md
    assert "CONFIRMED_REGRESSION" in md
