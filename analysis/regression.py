"""
WinScope - Performance Regression Comparison Engine.

Performs rigorous baseline-versus-candidate statistical comparisons:
- Percentile and distribution comparisons
- Welch's two-sample t-test & Mann-Whitney U test
- 95% Confidence intervals on mean delta
- Objective regression verdict with uncertainty guards
"""

import math
from typing import List, Dict, Any, Optional
import numpy as np
from scipy import stats

from analysis.engine import StatisticalAnalysisEngine


class PerformanceRegressionComparator:
    """
    Compares baseline and candidate performance time series.
    """

    @staticmethod
    def compare_metrics(
        baseline_series: List[float],
        candidate_series: List[float],
        metric_name: str,
        unit: str,
        regression_threshold_pct: float = 15.0,
        alpha: float = 0.05
    ) -> Dict[str, Any]:
        """
        Executes a comparative statistical test between two measurement runs.
        """
        b_clean = [x for x in baseline_series if x is not None and not math.isnan(x)]
        c_clean = [x for x in candidate_series if x is not None and not math.isnan(x)]

        b_stats = StatisticalAnalysisEngine.compute_summary_statistics(b_clean)
        c_stats = StatisticalAnalysisEngine.compute_summary_statistics(c_clean)

        n_b = len(b_clean)
        n_c = len(c_clean)

        # Insufficient sample guard
        if n_b < 3 or n_c < 3:
            return {
                "metric_name": metric_name,
                "unit": unit,
                "verdict": "INCONCLUSIVE",
                "reason": f"Insufficient sample size (Baseline: {n_b}, Candidate: {n_c})",
                "baseline_stats": b_stats,
                "candidate_stats": c_stats,
            }

        # Absolute difference and relative difference on median
        med_b = b_stats["median"]
        med_c = c_stats["median"]
        abs_diff = med_c - med_b
        rel_diff_pct = (abs_diff / med_b * 100.0) if med_b != 0 else 0.0

        mean_diff = c_stats["mean"] - b_stats["mean"]

        # Statistical hypothesis testing (Welch's t-test for unequal variances)
        ttest_pvalue = None
        mannwhitney_pvalue = None
        ci_lower = None
        ci_upper = None

        if not b_stats["is_zero_variance"] or not c_stats["is_zero_variance"]:
            try:
                t_stat, ttest_pvalue = stats.ttest_ind(c_clean, b_clean, equal_var=False)
                ttest_pvalue = float(ttest_pvalue) if not math.isnan(ttest_pvalue) else 1.0

                # 95% Confidence Interval for difference in means (Welch-Satterthwaite)
                s1, s2 = c_stats["std"], b_stats["std"]
                se_diff = math.sqrt((s1**2 / n_c) + (s2**2 / n_b)) if (s1 > 0 or s2 > 0) else 0.0
                if se_diff > 0:
                    df = ((s1**2 / n_c + s2**2 / n_b)**2) / (
                        (s1**2 / n_c)**2 / (n_c - 1) + (s2**2 / n_b)**2 / (n_b - 1)
                    )
                    t_crit = stats.t.ppf(1 - alpha / 2, df)
                    ci_lower = float(mean_diff - t_crit * se_diff)
                    ci_upper = float(mean_diff + t_crit * se_diff)
            except Exception:
                pass

            try:
                _, mw_p = stats.mannwhitneyu(c_clean, b_clean, alternative="two-sided")
                mannwhitney_pvalue = float(mw_p)
            except Exception:
                pass

        # Determine regression verdict
        is_statistically_significant = (
            ttest_pvalue is not None and ttest_pvalue < alpha
        ) or (
            mannwhitney_pvalue is not None and mannwhitney_pvalue < alpha
        )

        if is_statistically_significant and rel_diff_pct >= regression_threshold_pct:
            verdict = "CONFIRMED_REGRESSION"
            explanation = f"Statistically supported increase of +{rel_diff_pct:.2f}% (p={ttest_pvalue:.4f}) above {regression_threshold_pct}% threshold."
        elif is_statistically_significant and rel_diff_pct <= -regression_threshold_pct:
            verdict = "IMPROVEMENT"
            explanation = f"Statistically supported reduction of {rel_diff_pct:.2f}% (p={ttest_pvalue:.4f})."
        elif rel_diff_pct >= regression_threshold_pct and not is_statistically_significant:
            verdict = "POSSIBLE_REGRESSION_UNVERIFIED"
            explanation = f"Large apparent shift of +{rel_diff_pct:.2f}%, but high variance prevents statistical rejection of null hypothesis."
        else:
            verdict = "NO_REGRESSION"
            explanation = "Measured variation is within normal statistical baseline noise."

        return {
            "metric_name": metric_name,
            "unit": unit,
            "verdict": verdict,
            "explanation": explanation,
            "absolute_diff_median": abs_diff,
            "relative_diff_median_pct": rel_diff_pct,
            "mean_diff": mean_diff,
            "ci_95": (ci_lower, ci_upper) if (ci_lower is not None and ci_upper is not None) else None,
            "ttest_pvalue": ttest_pvalue,
            "mannwhitney_pvalue": mannwhitney_pvalue,
            "baseline_stats": b_stats,
            "candidate_stats": c_stats,
        }
