"""
WinScope - Telemetry Ingestion Pipeline.

Validates schemas, isolates malformed records into quarantine, deduplicates observations,
measures sampling interval regularity, and stores clean data into SQLite.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Tuple, Any

import numpy as np
from core.models import MetricObservation, SessionMetadata
from core.units import METRIC_CATALOG
from storage.db import TelemetryDatabase
from ingestion.quality import DataQualityReport


class TelemetryIngestionPipeline:
    """
    Ingests raw JSONL files into the durable SQLite store with strict schema validation.
    """

    def __init__(self, db: Optional[TelemetryDatabase] = None):
        self.db = db or TelemetryDatabase()

    def ingest_file(self, file_path: str) -> DataQualityReport:
        with open(file_path, "r", encoding="utf-8") as f:
            return self.ingest_stream(f)

    def ingest_stream(self, line_iterator) -> DataQualityReport:
        session_meta: Optional[SessionMetadata] = None
        accepted_observations: List[Tuple[MetricObservation, str]] = []
        quarantined: List[Tuple[str, str, Optional[str]]] = []  # (raw_payload, reason, session_id)
        seen_keys = set()
        duplicates_count = 0
        unavailable_metric_names = set()
        quarantine_reasons: Dict[str, int] = {}

        total_lines = 0

        for line in line_iterator:
            raw_line = line.strip()
            if not raw_line:
                continue

            total_lines += 1

            try:
                data = json.loads(raw_line)
            except Exception as ex:
                reason = f"JSON decode error: {str(ex)}"
                quarantined.append((raw_line, reason, session_meta.session_id if session_meta else None))
                quarantine_reasons[reason] = quarantine_reasons.get(reason, 0) + 1
                continue

            record_type = data.get("type")

            # Handle session header
            if record_type == "session_header":
                try:
                    session_meta = SessionMetadata(
                        session_id=data["session_id"],
                        start_time=datetime.fromisoformat(data["start_time"].replace("Z", "+00:00")),
                        host_name=data["host_name"],
                        os_version=data["os_version"],
                        sampling_interval_ms=data["sampling_interval_ms"],
                        collector_type=data.get("collector_type", "Unknown"),
                        collector_version=data.get("collector_version", "1.0.0"),
                        schema_version=data.get("schema_version", "1.0.0")
                    )
                except Exception as ex:
                    reason = f"Invalid session header: {str(ex)}"
                    quarantined.append((raw_line, reason, None))
                    quarantine_reasons[reason] = quarantine_reasons.get(reason, 0) + 1
                continue

            # Handle session footer
            if record_type == "session_footer":
                if session_meta and "end_time" in data:
                    session_meta.end_time = datetime.fromisoformat(data["end_time"].replace("Z", "+00:00"))
                continue

            # Standard metric observation
            try:
                obs = MetricObservation.model_validate(data)
                obs.validate_against_catalog()

                curr_session_id = session_meta.session_id if session_meta else "default_session"

                # Duplicate detection: (session_id, timestamp, metric_name, target_id)
                dedup_key = (curr_session_id, obs.timestamp.isoformat(), obs.metric_name, obs.target_id)
                if dedup_key in seen_keys:
                    duplicates_count += 1
                    reason = "Duplicate observation key"
                    quarantined.append((raw_line, reason, curr_session_id))
                    quarantine_reasons[reason] = quarantine_reasons.get(reason, 0) + 1
                    continue

                seen_keys.add(dedup_key)

                if obs.status in ("unavailable", "error"):
                    unavailable_metric_names.add(obs.metric_name)

                accepted_observations.append((obs, curr_session_id))

            except Exception as ex:
                reason = f"Schema / catalog validation error: {str(ex)}"
                sid = session_meta.session_id if session_meta else None
                quarantined.append((raw_line, reason, sid))
                quarantine_reasons[reason] = quarantine_reasons.get(reason, 0) + 1

        # Analyze sampling interval regularity and missing gaps
        expected_interval_ms = session_meta.sampling_interval_ms if session_meta else 1000
        interval_stats, missing_intervals = self._compute_sampling_intervals(
            accepted_observations, expected_interval_ms
        )

        # Database transaction
        with self.db.connection() as conn:
            # 1. Upsert session
            if session_meta:
                conn.execute("""
                INSERT OR REPLACE INTO sessions (
                    session_id, start_time, end_time, host_name, os_version,
                    sampling_interval_ms, collector_type, collector_version, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    session_meta.session_id,
                    session_meta.start_time.isoformat(),
                    session_meta.end_time.isoformat() if session_meta.end_time else None,
                    session_meta.host_name,
                    session_meta.os_version,
                    session_meta.sampling_interval_ms,
                    session_meta.collector_type,
                    session_meta.collector_version,
                    session_meta.schema_version
                ))

            # 2. Bulk insert accepted observations
            if accepted_observations:
                obs_rows = [
                    (
                        sid,
                        obs.timestamp.isoformat(),
                        obs.time_basis.value,
                        obs.metric_name,
                        obs.value,
                        obs.unit.value,
                        obs.source,
                        obs.target_id,
                        obs.status,
                        obs.error_message,
                        obs.schema_version
                    )
                    for obs, sid in accepted_observations
                ]
                conn.executemany("""
                INSERT INTO observations (
                    session_id, timestamp, time_basis, metric_name, value, unit,
                    source, target_id, status, error_message, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, obs_rows)

            # 3. Bulk insert quarantined records
            if quarantined:
                quarantine_rows = [(sid, payload, reason) for payload, reason, sid in quarantined]
                conn.executemany("""
                INSERT INTO quarantined_records (session_id, raw_payload, quarantine_reason)
                VALUES (?, ?, ?);
                """, quarantine_rows)

            # 4. Save data quality report
            report_id = str(uuid.uuid4())
            curr_sid = session_meta.session_id if session_meta else "default_session"
            conn.execute("""
            INSERT INTO data_quality_reports (
                report_id, session_id, total_records, accepted_records, quarantined_records,
                duplicate_records, missing_intervals, interval_mean_ms, interval_std_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                report_id,
                curr_sid,
                total_lines,
                len(accepted_observations),
                len(quarantined),
                duplicates_count,
                missing_intervals,
                interval_stats.get("mean"),
                interval_stats.get("std")
            ))

        total_accepted = len(accepted_observations)
        completeness = (total_accepted / total_lines * 100.0) if total_lines > 0 else 0.0

        return DataQualityReport(
            report_id=report_id,
            session_id=session_meta.session_id if session_meta else "unknown",
            total_records=total_lines,
            accepted_records=total_accepted,
            quarantined_records=len(quarantined),
            duplicate_records=duplicates_count,
            missing_intervals=missing_intervals,
            sampling_interval_expected_ms=expected_interval_ms,
            interval_mean_ms=interval_stats.get("mean"),
            interval_std_ms=interval_stats.get("std"),
            interval_min_ms=interval_stats.get("min"),
            interval_max_ms=interval_stats.get("max"),
            unavailable_metrics=sorted(list(unavailable_metric_names)),
            quarantine_reasons=quarantine_reasons,
            completeness_pct=completeness
        )

    def _compute_sampling_intervals(
        self,
        accepted: List[Tuple[MetricObservation, str]],
        expected_interval_ms: int
    ) -> Tuple[Dict[str, float], int]:
        """Calculates inter-sample deltas across unique timestamps."""
        if not accepted:
            return {}, 0

        # Extract timestamps for one reliable metric (e.g., cpu.utilization.pct or system.uptime)
        timestamps = sorted(list({
            obs.timestamp for obs, _ in accepted if obs.metric_name == "cpu.utilization.pct"
        }))

        if len(timestamps) < 2:
            return {"mean": float(expected_interval_ms), "std": 0.0, "min": float(expected_interval_ms), "max": float(expected_interval_ms)}, 0

        deltas_ms = [
            (t2 - t1).total_seconds() * 1000.0
            for t1, t2 in zip(timestamps[:-1], timestamps[1:])
        ]

        # Missing interval threshold: if gap is >= 1.75 * expected interval
        threshold = expected_interval_ms * 1.75
        missing_count = sum(1 for d in deltas_ms if d >= threshold)

        return {
            "mean": float(np.mean(deltas_ms)),
            "std": float(np.std(deltas_ms)),
            "min": float(np.min(deltas_ms)),
            "max": float(np.max(deltas_ms))
        }, missing_count
