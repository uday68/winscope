-- ============================================================================
-- WinScope Telemetry SQL Query Catalog
-- Compatible with SQLite 3.35+
-- ============================================================================

-- 1. CPU Utilization Time Series with Moving Average
-- Calculates 3-sample centered rolling average of processor utilization
SELECT 
    session_id,
    timestamp,
    value AS cpu_pct,
    AVG(value) OVER (
        PARTITION BY session_id 
        ORDER BY timestamp 
        ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING
    ) AS rolling_avg_cpu
FROM observations
WHERE metric_name = 'cpu.utilization.pct' AND status = 'ok'
ORDER BY session_id, timestamp;


-- 2. Physical Memory Utilization by Session
-- Summary statistics of memory pressure across sessions
SELECT 
    session_id,
    COUNT(*) AS sample_count,
    ROUND(MIN(value), 2) AS min_mem_pct,
    ROUND(AVG(value), 2) AS avg_mem_pct,
    ROUND(MAX(value), 2) AS max_mem_pct
FROM observations
WHERE metric_name = 'memory.physical.utilization.pct' AND status = 'ok'
GROUP BY session_id;


-- 3. Disk Read/Write Throughput Aggregation
-- Aggregates I/O throughput in MB/s per session
SELECT 
    session_id,
    metric_name,
    COUNT(*) AS sample_count,
    ROUND(AVG(value) / 1048576.0, 3) AS avg_mb_per_sec,
    ROUND(MAX(value) / 1048576.0, 3) AS peak_mb_per_sec
FROM observations
WHERE metric_name IN ('disk.io.read.bytes_per_sec', 'disk.io.write.bytes_per_sec')
GROUP BY session_id, metric_name;


-- 4. Missing Telemetry Interval Detection
-- Identifies sampling gaps where time delta exceeds 1.75x the session's configured interval
WITH LaggedSamples AS (
    SELECT 
        o.session_id,
        o.timestamp,
        s.sampling_interval_ms,
        LAG(o.timestamp) OVER (PARTITION BY o.session_id ORDER BY o.timestamp) AS prev_timestamp
    FROM observations o
    JOIN sessions s ON o.session_id = s.session_id
    WHERE o.metric_name = 'cpu.utilization.pct'
)
SELECT 
    session_id,
    prev_timestamp AS gap_start,
    timestamp AS gap_end,
    ROUND((julianday(timestamp) - julianday(prev_timestamp)) * 86400000.0, 1) AS observed_gap_ms,
    sampling_interval_ms AS expected_interval_ms
FROM LaggedSamples
WHERE prev_timestamp IS NOT NULL
  AND (julianday(timestamp) - julianday(prev_timestamp)) * 86400000.0 > (sampling_interval_ms * 1.75);


-- 5. Process Resource Consumption Ranking
-- Compares CPU and peak working set across monitored PIDs
SELECT 
    target_id AS process_identifier,
    COUNT(CASE WHEN metric_name = 'process.cpu.utilization.pct' THEN 1 END) AS cpu_samples,
    ROUND(AVG(CASE WHEN metric_name = 'process.cpu.utilization.pct' THEN value END), 2) AS avg_cpu_pct,
    ROUND(MAX(CASE WHEN metric_name = 'process.memory.working_set.bytes' THEN value END) / 1048576.0, 2) AS peak_working_set_mb
FROM observations
WHERE target_id IS NOT NULL AND status = 'ok'
GROUP BY target_id
ORDER BY avg_cpu_pct DESC;


-- 6. Baseline vs Candidate Comparative Shift
-- Compares average CPU utilization across two designated sessions
SELECT 
    base.metric_name,
    ROUND(base.avg_val, 2) AS baseline_avg,
    ROUND(cand.avg_val, 2) AS candidate_avg,
    ROUND(cand.avg_val - base.avg_val, 2) AS absolute_shift,
    ROUND(((cand.avg_val - base.avg_val) / base.avg_val) * 100.0, 2) AS relative_shift_pct
FROM (
    SELECT metric_name, AVG(value) AS avg_val
    FROM observations
    WHERE session_id = '5eb20de7-124a-4f00-ab36-97e79d5ba075' -- Example Baseline Session
    GROUP BY metric_name
) base
JOIN (
    SELECT metric_name, AVG(value) AS avg_val
    FROM observations
    WHERE session_id = '5eb20de7-124a-4f00-ab36-97e79d5ba075' -- Example Candidate Session
    GROUP BY metric_name
) cand ON base.metric_name = cand.metric_name;
