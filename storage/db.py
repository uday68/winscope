"""
WinScope - SQLite Telemetry Database Layer.

Provides durable local storage for sessions, time-series observations,
quarantined records, and data quality summaries.
"""

import sqlite3
import os
from contextlib import contextmanager
from typing import Optional, List, Dict, Any
from datetime import datetime


DEFAULT_DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "winscope.db"))


class TelemetryDatabase:
    """
    Manages SQLite database connections, schema migrations, and indexing.
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.init_schema()

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def init_schema(self) -> None:
        with self.connection() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                start_time TEXT NOT NULL,
                end_time TEXT,
                host_name TEXT NOT NULL,
                os_version TEXT NOT NULL,
                sampling_interval_ms INTEGER NOT NULL,
                collector_type TEXT NOT NULL,
                collector_version TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
            );

            CREATE TABLE IF NOT EXISTS observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                time_basis TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                value REAL,
                unit TEXT NOT NULL,
                source TEXT NOT NULL,
                target_id TEXT,
                status TEXT NOT NULL,
                error_message TEXT,
                schema_version TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            );

            CREATE TABLE IF NOT EXISTS quarantined_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                raw_payload TEXT NOT NULL,
                quarantine_reason TEXT NOT NULL,
                quarantined_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
            );

            CREATE TABLE IF NOT EXISTS data_quality_reports (
                report_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                total_records INTEGER NOT NULL,
                accepted_records INTEGER NOT NULL,
                quarantined_records INTEGER NOT NULL,
                duplicate_records INTEGER NOT NULL,
                missing_intervals INTEGER NOT NULL,
                interval_mean_ms REAL,
                interval_std_ms REAL,
                generated_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            );

            -- Indexes for fast time-series slicing and metrics filtering
            CREATE INDEX IF NOT EXISTS idx_obs_session_metric_time 
                ON observations(session_id, metric_name, timestamp);

            CREATE INDEX IF NOT EXISTS idx_obs_metric_time 
                ON observations(metric_name, timestamp);

            CREATE INDEX IF NOT EXISTS idx_obs_target 
                ON observations(target_id, timestamp);
            """)
