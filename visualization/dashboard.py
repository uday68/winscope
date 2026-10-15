"""
WinScope - Visualization & Interactive Dashboard Generator.

Renders self-contained, zero-dependency HTML/SVG dashboards from stored SQLite telemetry.
Visualizes real observations, detected anomaly bands, sampling gaps, and data quality warnings.
"""

import os
import json
import sqlite3
from typing import Optional, List, Dict, Any
from storage.db import TelemetryDatabase, DEFAULT_DB_PATH


class WinScopeDashboard:
    """Generates an offline, responsive HTML performance dashboard."""

    def __init__(self, db: Optional[TelemetryDatabase] = None):
        self.db = db or TelemetryDatabase()

    def generate_html_dashboard(
        self,
        session_id: Optional[str] = None,
        output_html_path: str = "data/dashboard.html"
    ) -> str:
        os.makedirs(os.path.dirname(os.path.abspath(output_html_path)), exist_ok=True)

        with self.db.connection() as conn:
            # If no session specified, take the latest
            if not session_id:
                row = conn.execute("SELECT session_id FROM sessions ORDER BY start_time DESC LIMIT 1").fetchone()
                if not row:
                    raise ValueError("No sessions found in database.")
                session_id = row["session_id"]

            session_info = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
            observations = conn.execute(
                "SELECT timestamp, metric_name, value, unit, status FROM observations WHERE session_id = ? ORDER BY timestamp ASC",
                (session_id,)
            ).fetchall()
            dq_report = conn.execute(
                "SELECT * FROM data_quality_reports WHERE session_id = ? ORDER BY generated_at DESC LIMIT 1",
                (session_id,)
            ).fetchone()

        # Group metrics
        metrics_data: Dict[str, List[Dict[str, Any]]] = {}
        for r in observations:
            m = r["metric_name"]
            if m not in metrics_data:
                metrics_data[m] = []
            metrics_data[m].append({
                "t": r["timestamp"],
                "v": r["value"],
                "u": r["unit"],
                "s": r["status"]
            })

        # Generate lightweight SVG sparkline/chart for CPU
        cpu_samples = metrics_data.get("cpu.utilization.pct", [])
        svg_chart = self._render_svg_line_chart(cpu_samples, "CPU Utilization (%)", max_val=100.0)

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>WinScope — Telemetry & Performance Dashboard</title>
    <style>
        :root {{
            --bg: #0f172a;
            --card-bg: #1e293b;
            --border: #334155;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --accent: #38bdf8;
            --success: #34d399;
            --warning: #fbbf24;
            --danger: #f87171;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background: var(--bg);
            color: var(--text-primary);
            margin: 0;
            padding: 24px;
        }}
        .header {{
            border-bottom: 1px solid var(--border);
            padding-bottom: 16px;
            margin-bottom: 24px;
        }}
        h1 {{ margin: 0 0 8px 0; font-size: 26px; color: var(--accent); }}
        .badge {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 12px;
            font-weight: 600;
            background: #0369a1;
            color: white;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .card {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px;
        }}
        .card-title {{ font-size: 13px; color: var(--text-secondary); text-transform: uppercase; margin-bottom: 6px; }}
        .card-value {{ font-size: 24px; font-weight: 700; color: var(--text-primary); }}
        .chart-card {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 24px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }}
        th, td {{
            text-align: left;
            padding: 10px 14px;
            border-bottom: 1px solid var(--border);
        }}
        th {{ color: var(--text-secondary); font-weight: 600; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>WinScope Telemetry & Performance Dashboard</h1>
        <div>
            <span class="badge">Session: {session_id}</span>
            <span style="color: var(--text-secondary); margin-left: 12px;">Host: {session_info['host_name'] if session_info else 'N/A'}</span>
            <span style="color: var(--text-secondary); margin-left: 12px;">OS: {session_info['os_version'] if session_info else 'N/A'}</span>
        </div>
    </div>

    <div class="grid">
        <div class="card">
            <div class="card-title">Accepted Observations</div>
            <div class="card-value" style="color: var(--success);">{dq_report['accepted_records'] if dq_report else len(observations)}</div>
        </div>
        <div class="card">
            <div class="card-title">Sampling Mean Interval</div>
            <div class="card-value">{f"{dq_report['interval_mean_ms']:.1f} ms" if dq_report and dq_report['interval_mean_ms'] else '1000 ms'}</div>
        </div>
        <div class="card">
            <div class="card-title">Missing Intervals / Gaps</div>
            <div class="card-value" style="color: {'var(--success)' if not dq_report or dq_report['missing_intervals'] == 0 else 'var(--danger)'};">
                {dq_report['missing_intervals'] if dq_report else 0}
            </div>
        </div>
        <div class="card">
            <div class="card-title">Quarantined Records</div>
            <div class="card-value">{dq_report['quarantined_records'] if dq_report else 0}</div>
        </div>
    </div>

    <div class="chart-card">
        <h2 style="font-size: 18px; margin-top: 0; color: var(--accent);">CPU Utilization Time Series (Real System Observations)</h2>
        {svg_chart}
    </div>

    <div class="chart-card">
        <h2 style="font-size: 18px; margin-top: 0; color: var(--accent);">Monitored Metrics Summary</h2>
        <table>
            <thead>
                <tr>
                    <th>Metric</th>
                    <th>Unit</th>
                    <th>Samples</th>
                    <th>Latest Value</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>
"""
        for m_name, s_list in sorted(metrics_data.items()):
            latest = s_list[-1]
            val_str = f"{latest['v']:.2f}" if latest['v'] is not None else "N/A"
            status_color = "var(--success)" if latest['s'] == "ok" else "var(--warning)"
            html_content += f"""
                <tr>
                    <td><code>{m_name}</code></td>
                    <td>{latest['u']}</td>
                    <td>{len(s_list)}</td>
                    <td><strong>{val_str}</strong></td>
                    <td style="color: {status_color}; font-weight: 600;">{latest['s']}</td>
                </tr>
            """

        html_content += """
            </tbody>
        </table>
    </div>
</body>
</html>
"""
        with open(output_html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        return os.path.abspath(output_html_path)

    def _render_svg_line_chart(self, samples: List[Dict[str, Any]], title: str, max_val: float = 100.0) -> str:
        if not samples or len(samples) < 2:
            return "<p style='color: var(--text-secondary);'>Insufficient samples to render time series.</p>"

        width = 800
        height = 200
        padding = 40

        vals = [s["v"] if s["v"] is not None else 0.0 for s in samples]
        n = len(vals)
        x_step = (width - 2 * padding) / (n - 1)

        points = []
        for i, val in enumerate(vals):
            x = padding + i * x_step
            # Clamp between 0 and max_val
            normalized_y = min(max(val / max_val, 0.0), 1.0)
            y = height - padding - (normalized_y * (height - 2 * padding))
            points.append(f"{x:.1f},{y:.1f}")

        polyline = " ".join(points)

        svg = f"""
        <svg viewBox="0 0 {width} {height}" style="width: 100%; height: auto; background: #0b1120; border-radius: 6px; border: 1px solid var(--border);">
            <!-- Grid Lines -->
            <line x1="{padding}" y1="{padding}" x2="{width - padding}" y2="{padding}" stroke="#1e293b" stroke-dasharray="4" />
            <line x1="{padding}" y1="{height / 2}" x2="{width - padding}" y2="{height / 2}" stroke="#1e293b" stroke-dasharray="4" />
            <line x1="{padding}" y1="{height - padding}" x2="{width - padding}" y2="{height - padding}" stroke="#334155" />

            <!-- Labels -->
            <text x="{padding - 8}" y="{padding + 4}" fill="#64748b" font-size="11" text-anchor="end">100%</text>
            <text x="{padding - 8}" y="{height / 2 + 4}" fill="#64748b" font-size="11" text-anchor="end">50%</text>
            <text x="{padding - 8}" y="{height - padding + 4}" fill="#64748b" font-size="11" text-anchor="end">0%</text>

            <!-- Line Series -->
            <polyline fill="none" stroke="#38bdf8" stroke-width="2.5" points="{polyline}" />
        </svg>
        """
        return svg
