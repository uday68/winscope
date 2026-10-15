"""
WinScope - Regression Diagnostic Report Generator.

Emits structured JSON and rich Markdown / HTML reports detailing
comparative metric shifts, sample counts, data quality, and limitations.
"""

import json
from datetime import datetime, timezone
from typing import Dict, Any, List


class DiagnosticReportGenerator:
    """Generates machine-readable and human-readable diagnostic reports."""

    @staticmethod
    def generate_json_report(
        baseline_session_id: str,
        candidate_session_id: str,
        comparisons: List[Dict[str, Any]],
        limitations: List[str]
    ) -> Dict[str, Any]:
        return {
            "report_type": "WinScope_Performance_Regression_Report",
            "schema_version": "1.0.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "baseline_session_id": baseline_session_id,
            "candidate_session_id": candidate_session_id,
            "comparisons": comparisons,
            "known_limitations_and_confounders": limitations,
        }

    @staticmethod
    def generate_markdown_report(report_data: Dict[str, Any]) -> str:
        b_id = report_data["baseline_session_id"]
        c_id = report_data["candidate_session_id"]
        ts = report_data["generated_at"]

        lines = [
            f"# WinScope — Performance Regression Diagnostic Report",
            f"**Generated At (UTC):** `{ts}`  ",
            f"**Baseline Session:** `{b_id}`  ",
            f"**Candidate Session:** `{c_id}`  ",
            "",
            "## 1. Executive Summary & Verdicts",
            "| Metric | Unit | Baseline (p50) | Candidate (p50) | Δ (Abs) | Δ (%) | p-value | Verdict |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
        ]

        for comp in report_data["comparisons"]:
            metric = comp["metric_name"]
            unit = comp["unit"]
            b_med = comp.get("baseline_stats", {}).get("median")
            c_med = comp.get("candidate_stats", {}).get("median")
            abs_d = comp.get("absolute_diff_median")
            rel_d = comp.get("relative_diff_median_pct")
            p_val = comp.get("ttest_pvalue")
            verdict = comp["verdict"]

            b_str = f"{b_med:.2f}" if b_med is not None else "N/A"
            c_str = f"{c_med:.2f}" if c_med is not None else "N/A"
            abs_str = f"{abs_d:+.2f}" if abs_d is not None else "N/A"
            rel_str = f"{rel_d:+.1f}%" if rel_d is not None else "N/A"
            p_str = f"{p_val:.4f}" if p_val is not None else "N/A"

            lines.append(f"| `{metric}` | `{unit}` | {b_str} | {c_str} | {abs_str} | {rel_str} | {p_str} | **{verdict}** |")

        lines.extend([
            "",
            "## 2. Detailed Statistical Breakdown",
        ])

        for comp in report_data["comparisons"]:
            metric = comp["metric_name"]
            explanation = comp.get("explanation", "")
            ci = comp.get("ci_95")
            ci_str = f"[{ci[0]:.2f}, {ci[1]:.2f}]" if ci else "N/A"

            b_stat = comp.get("baseline_stats", {})
            c_stat = comp.get("candidate_stats", {})

            lines.extend([
                f"### `{metric}` ({comp['unit']})",
                f"- **Verdict:** {comp['verdict']} — {explanation}",
                f"- **95% Confidence Interval for Mean Difference:** {ci_str}",
                f"- **Baseline Distribution:** N={b_stat.get('count')}, Median={b_stat.get('median')}, MAD={b_stat.get('mad')}, p90={b_stat.get('p90')}, p99={b_stat.get('p99')}",
                f"- **Candidate Distribution:** N={c_stat.get('count')}, Median={c_stat.get('median')}, MAD={c_stat.get('mad')}, p90={c_stat.get('p90')}, p99={c_stat.get('p99')}",
                ""
            ])

        lines.extend([
            "## 3. Engineering Limitations & Confounders",
        ])
        for lim in report_data.get("known_limitations_and_confounders", []):
            lines.append(f"- {lim}")

        lines.append("\n*Report produced deterministically by WinScope Analytics Engine.*")
        return "\n".join(lines)
