-- 02_dispatch_funnel.sql
-- Accept-to-deliver funnel: CTEs + window functions.
-- Grain: one row per zone-hour. Metrics: requests (accepts), completed
-- (deliveries), median / p90 accept-to-deliver minutes, share over 30 min
-- and over 240 min, plus a 3-hour rolling median and the zone's rank by p90.
-- Durations over 720 min (12h) are excluded from the speed percentiles
-- (flagged in 01_data_quality_checks.sql) but counted in the *_all rows.
-- Run: duckdb -c ".read sql/02_dispatch_funnel.sql"

WITH valid AS (
    SELECT *,
           date_trunc('hour', accept_dt) AS accept_hour
    FROM read_csv('data/raw/lade_delivery_events.csv', header = true)
    WHERE accept_to_deliver_min BETWEEN 0 AND 720
),
per_order AS (
    SELECT *,
           -- rank of this order's duration within its zone-hour (slowest first)
           row_number() OVER (PARTITION BY city, zone_id, accept_hour
                              ORDER BY accept_to_deliver_min DESC) AS slowest_rank_in_hour,
           count(*) OVER (PARTITION BY city, zone_id, accept_hour) AS orders_in_hour
    FROM valid
),
hourly AS (
    SELECT city, zone_id, accept_hour,
           count(*) AS requests,
           median(accept_to_deliver_min) AS median_min,
           quantile_cont(accept_to_deliver_min, 0.9) AS p90_min,
           quantile_cont(accept_to_deliver_min, 0.5) AS p50_min,
           avg(accept_to_deliver_min) AS mean_min,
           100.0 * sum(CASE WHEN accept_to_deliver_min > 30 THEN 1 ELSE 0 END) / count(*) AS pct_over_30min,
           100.0 * sum(CASE WHEN accept_to_deliver_min > 240 THEN 1 ELSE 0 END) / count(*) AS pct_over_240min,
           count(DISTINCT courier_id) AS active_couriers
    FROM per_order
    GROUP BY city, zone_id, accept_hour
),
rolling AS (
    SELECT *,
           -- 3-hour rolling median of the hourly median, within each zone
           median(median_min) OVER (PARTITION BY city, zone_id
                                    ORDER BY accept_hour
                                    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS rolling_3h_median_min,
           -- Rank reported p90 so display-precision ties are deterministic.
           rank() OVER (PARTITION BY accept_hour ORDER BY round(p90_min, 1) DESC) AS slowest_zone_rank_in_hour
    FROM hourly
)
SELECT city, zone_id, accept_hour, requests, active_couriers,
       round(p50_min, 1) AS median_min, round(p90_min, 1) AS p90_min, round(mean_min, 1) AS mean_min,
       round(pct_over_30min, 1) AS pct_over_30min, round(pct_over_240min, 1) AS pct_over_240min,
       round(rolling_3h_median_min, 1) AS rolling_3h_median_min,
       slowest_zone_rank_in_hour
FROM rolling
ORDER BY city, zone_id, accept_hour;
