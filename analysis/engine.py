"""
WinScope - Statistical Telemetry Analysis Engine.

Implements interpretable, robust statistical methods:
- Rolling mean and variance
- Median and Median Absolute Deviation (MAD)
- Robust modified Z-score
- Sustained deviation and changepoint detection
- Zero-variance and sample-size safety guards
"""

import math
from typing import List, Dict, Any, Optional, Tuple
import numpy as np


class StatisticalAnalysisEngine:
    """
    Analyzes telemetry time series for anomalies, distribution shifts, and outliers.
    """

    @staticmethod
    def compute_summary_statistics(series: List[float]) -> Dict[str, Any]:
        """Computes parametric and non-parametric summary stats with zero-variance safety."""
        clean = [x for x in series if x is not None and not math.isnan(x)]
        n = len(clean)
        if n == 0:
            return {"count": 0, "mean": None, "median": None, "std": None, "mad": None}

        arr = np.array(clean, dtype=float)
        mean_val = float(np.mean(arr))
        median_val = float(np.median(arr))
        std_val = float(np.std(arr, ddof=1)) if n > 1 else 0.0

        # Median Absolute Deviation (MAD)
        abs_dev = np.abs(arr - median_val)
        mad_val = float(np.median(abs_dev))

        p50 = median_val
        p90 = float(np.percentile(arr, 90))
        p99 = float(np.percentile(arr, 99))
        min_val = float(np.min(arr))
        max_val = float(np.max(arr))

        return {
            "count": n,
            "mean": mean_val,
            "median": median_val,
            "std": std_val,
            "mad": mad_val,
            "min": min_val,
            "p50": p50,
            "p90": p90,
            "p99": p99,
            "max": max_val,
            "is_zero_variance": (std_val == 0.0 or mad_val == 0.0)
        }

    @staticmethod
    def compute_robust_z_scores(series: List[float], threshold: float = 3.5) -> List[Optional[float]]:
        """
        Computes Modified Z-score using Boris Iglewicz and David Hoaglin formula:
        M_i = 0.6745 * (x_i - median) / MAD
        Returns None for invalid samples.
        """
        clean = [x for x in series if x is not None and not math.isnan(x)]
        if len(clean) < 3:
            return [None if x is None else 0.0 for x in series]

        arr = np.array(clean, dtype=float)
        med = np.median(arr)
        mad = np.median(np.abs(arr - med))

        scores = []
        for x in series:
            if x is None or math.isnan(x):
                scores.append(None)
            elif mad > 1e-9:
                z = 0.6745 * (x - med) / mad
                scores.append(float(z))
            else:
                # Fallback to standard deviation if MAD is 0 (identical values)
                std = np.std(arr)
                if std > 1e-9:
                    scores.append(float((x - med) / std))
                else:
                    scores.append(0.0)
        return scores

    @staticmethod
    def detect_anomalies(
        series: List[float],
        timestamps: List[str],
        z_threshold: float = 3.0,
        sustained_window: int = 3
    ) -> Dict[str, Any]:
        """
        Distinguishes between:
        1. Single transient outliers (isolated sample > threshold)
        2. Sustained deviations (>= sustained_window consecutive samples > threshold)
        """
        z_scores = StatisticalAnalysisEngine.compute_robust_z_scores(series, threshold=z_threshold)
        transient_outliers = []
        sustained_deviations = []

        consecutive_count = 0
        consecutive_start_idx = None

        for idx, (val, z, ts) in enumerate(zip(series, z_scores, timestamps)):
            if z is not None and abs(z) >= z_threshold:
                if consecutive_count == 0:
                    consecutive_start_idx = idx
                consecutive_count += 1
            else:
                if consecutive_count >= sustained_window:
                    sustained_deviations.append({
                        "start_time": timestamps[consecutive_start_idx],
                        "end_time": timestamps[idx - 1],
                        "samples": consecutive_count,
                        "mean_z_score": float(np.mean([abs(z_scores[i]) for i in range(consecutive_start_idx, idx)]))
                    })
                elif consecutive_count > 0:
                    for i in range(consecutive_start_idx, idx):
                        transient_outliers.append({
                            "timestamp": timestamps[i],
                            "value": series[i],
                            "z_score": z_scores[i]
                        })
                consecutive_count = 0

        # Handle tail
        if consecutive_count >= sustained_window:
            sustained_deviations.append({
                "start_time": timestamps[consecutive_start_idx],
                "end_time": timestamps[-1],
                "samples": consecutive_count,
                "mean_z_score": float(np.mean([abs(z_scores[i]) for i in range(consecutive_start_idx, len(series))]))
            })
        elif consecutive_count > 0:
            for i in range(consecutive_start_idx, len(series)):
                transient_outliers.append({
                    "timestamp": timestamps[i],
                    "value": series[i],
                    "z_score": z_scores[i]
                })

        return {
            "transient_outliers": transient_outliers,
            "sustained_deviations": sustained_deviations,
            "total_anomalies": len(transient_outliers) + sum(d["samples"] for d in sustained_deviations)
        }
