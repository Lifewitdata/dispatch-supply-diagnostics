-- 01_data_quality_checks.sql
-- Data quality checks on data/raw/lade_delivery_events.csv (LaDe-D sample,
-- 2022-06-01 to 2022-06-14, 5 cities). Run with DuckDB:
--   duckdb -c ".read sql/01_data_quality_checks.sql"
-- or via python/01_run_sql_pipeline.py, which logs each check and writes
-- data/processed/dq_alerts.csv.
-- Every check returns: check_name, failed_rows, total_rows, fail_pct, verdict.
-- Verdict thresholds: FAIL if fail_pct > 5%, WARN if > 0.5%, else PASS.

WITH base AS (
    SELECT * FROM read_csv('data/raw/lade_delivery_events.csv', header = true)
),
counts AS (
    SELECT count(*) AS n FROM base
)
SELECT 'duplicate_order_id' AS check_name,
       (SELECT count(*) FROM (SELECT order_id FROM base GROUP BY order_id HAVING count(*) > 1)) AS failed_rows,
       (SELECT n FROM counts) AS total_rows,
       100.0 * (SELECT count(*) FROM (SELECT order_id FROM base GROUP BY order_id HAVING count(*) > 1)) / (SELECT n FROM counts) AS fail_pct,
       CASE WHEN 100.0 * (SELECT count(*) FROM (SELECT order_id FROM base GROUP BY order_id HAVING count(*) > 1)) / (SELECT n FROM counts) > 5 THEN 'FAIL'
            WHEN 100.0 * (SELECT count(*) FROM (SELECT order_id FROM base GROUP BY order_id HAVING count(*) > 1)) / (SELECT n FROM counts) > 0.5 THEN 'WARN' ELSE 'PASS' END AS verdict
UNION ALL
SELECT 'negative_accept_to_deliver_min', count(*), (SELECT n FROM counts),
       100.0 * count(*) / (SELECT n FROM counts),
       CASE WHEN 100.0 * count(*) / (SELECT n FROM counts) > 5 THEN 'FAIL'
            WHEN 100.0 * count(*) / (SELECT n FROM counts) > 0.5 THEN 'WARN' ELSE 'PASS' END
FROM base WHERE accept_to_deliver_min < 0
UNION ALL
SELECT 'duration_over_12h', count(*), (SELECT n FROM counts),
       100.0 * count(*) / (SELECT n FROM counts),
       CASE WHEN 100.0 * count(*) / (SELECT n FROM counts) > 5 THEN 'FAIL'
            WHEN 100.0 * count(*) / (SELECT n FROM counts) > 0.5 THEN 'WARN' ELSE 'PASS' END
FROM base WHERE accept_to_deliver_min > 720
UNION ALL
SELECT 'null_accept_gps', count(*), (SELECT n FROM counts),
       100.0 * count(*) / (SELECT n FROM counts),
       CASE WHEN 100.0 * count(*) / (SELECT n FROM counts) > 5 THEN 'FAIL'
            WHEN 100.0 * count(*) / (SELECT n FROM counts) > 0.5 THEN 'WARN' ELSE 'PASS' END
FROM base WHERE accept_gps_lng IS NULL OR accept_gps_lat IS NULL
UNION ALL
SELECT 'null_delivery_gps', count(*), (SELECT n FROM counts),
       100.0 * count(*) / (SELECT n FROM counts),
       CASE WHEN 100.0 * count(*) / (SELECT n FROM counts) > 5 THEN 'FAIL'
            WHEN 100.0 * count(*) / (SELECT n FROM counts) > 0.5 THEN 'WARN' ELSE 'PASS' END
FROM base WHERE delivery_gps_lng IS NULL OR delivery_gps_lat IS NULL
UNION ALL
SELECT 'null_zone_or_courier', count(*), (SELECT n FROM counts),
       100.0 * count(*) / (SELECT n FROM counts),
       CASE WHEN 100.0 * count(*) / (SELECT n FROM counts) > 5 THEN 'FAIL'
            WHEN 100.0 * count(*) / (SELECT n FROM counts) > 0.5 THEN 'WARN' ELSE 'PASS' END
FROM base WHERE zone_id IS NULL OR courier_id IS NULL
UNION ALL
SELECT 'delivery_before_accept_dt', count(*), (SELECT n FROM counts),
       100.0 * count(*) / (SELECT n FROM counts),
       CASE WHEN 100.0 * count(*) / (SELECT n FROM counts) > 5 THEN 'FAIL'
            WHEN 100.0 * count(*) / (SELECT n FROM counts) > 0.5 THEN 'WARN' ELSE 'PASS' END
FROM base WHERE delivery_dt < accept_dt
UNION ALL
SELECT 'date_ds_mismatch', count(*), (SELECT n FROM counts),
       100.0 * count(*) / (SELECT n FROM counts),
       CASE WHEN 100.0 * count(*) / (SELECT n FROM counts) > 5 THEN 'FAIL'
            WHEN 100.0 * count(*) / (SELECT n FROM counts) > 0.5 THEN 'WARN' ELSE 'PASS' END
FROM base WHERE date != make_date(2022, CAST(ds / 100 AS INTEGER), ds % 100)
;
