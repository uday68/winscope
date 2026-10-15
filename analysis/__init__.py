"""WinScope Analysis Package."""
from analysis.engine import StatisticalAnalysisEngine
from analysis.regression import PerformanceRegressionComparator
from analysis.report import DiagnosticReportGenerator

__all__ = [
    "StatisticalAnalysisEngine",
    "PerformanceRegressionComparator",
    "DiagnosticReportGenerator",
]
