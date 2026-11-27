-- 03_supply_demand_imbalance.sql
-- Supply-demand imbalance on data/raw/hourly_supply_demand.csv.
-- Grain: one row per zone-hour. Metrics:
--   zeroes_rate_pct  = % of zone-hours in the group with eyeballs = 0
--   fulfilment_pct   = requests / expected_requests (baseline = expanding
--                      median of prior days, same zone + hour-of-day)
--   courier_utilisation_pct = active_couriers / eyeballs
--   lost_orders_est  = modelled shortfall, counted ONLY in hours with
--                      eyeballs <= 1 (see build_data.py for why).
-- Groups: (a) by city, (b) by city + hour band, (c) worst zones.
-- Run: duckdb -c ".read sql/03_supply_demand_imbalance.sql"

WITH h AS (
    SELECT *,
           CASE WHEN hour BETWEEN 0 AND 5 THEN 'night 00-05'
                WHEN hour BETWEEN 6 AND 11 THEN 'morning 06-11'
                WHEN hour BETWEEN 12 AND 16 THEN 'afternoon 12-16'
                WHEN hour BETWEEN 17 AND 22 THEN 'evening 17-22'
                ELSE 'late 23' END AS hour_band
    FROM read_csv('data/raw/hourly_supply_demand.csv', header = true)
)
-- (a) by city
SELECT 'by_city' AS grain, city AS group_1, NULL AS group_2,
       count(*) AS zone_hours,
       round(100.0 * avg(zeroes), 1) AS zeroes_rate_pct,
       round(median(fulfilment_pct), 1) AS avg_fulfilment_pct,
       round(avg(courier_utilisation_pct), 1) AS avg_utilisation_pct,
       round(sum(lost_orders_est), 1) AS lost_orders_est,
       sum(requests) AS requests, sum(completed) AS completed
FROM h GROUP BY city
UNION ALL
-- (b) by city + hour band
SELECT 'by_city_hour_band', city, hour_band,
       count(*),
       round(100.0 * avg(zeroes), 1),
       round(avg(fulfilment_pct), 1),
       round(avg(courier_utilisation_pct), 1),
       round(sum(lost_orders_est), 1),
       sum(requests), sum(completed)
FROM h GROUP BY city, hour_band
UNION ALL
-- (c) worst 15 zones by modelled lost orders (LIMIT inside the subquery:
-- a LIMIT on the whole UNION would return the city totals instead)
SELECT * FROM (
    SELECT 'worst_zones' AS grain, city AS group_1, CAST(zone_id AS VARCHAR) AS group_2,
           count(*) AS zone_hours,
           round(100.0 * avg(zeroes), 1) AS zeroes_rate_pct,
           round(median(fulfilment_pct), 1) AS avg_fulfilment_pct,
           round(avg(courier_utilisation_pct), 1) AS avg_utilisation_pct,
           round(sum(lost_orders_est), 1) AS lost_orders_est,
           sum(requests) AS requests, sum(completed) AS completed
    FROM h GROUP BY city, zone_id
    ORDER BY lost_orders_est DESC
    LIMIT 15
) AS results
ORDER BY CASE grain
             WHEN 'by_city' THEN 1
             WHEN 'by_city_hour_band' THEN 2
             ELSE 3
         END,
         CASE WHEN grain = 'worst_zones' THEN lost_orders_est END DESC,
         group_1,
         group_2;
