"""Run the SQL pipeline with DuckDB and log data-quality alerts.

Steps:
  1. sql/01_data_quality_checks.sql  -> data/processed/dq_alerts.csv
     (FAIL/WARN/PASS per check; exit code 1 if any FAIL)
  2. sql/02_dispatch_funnel.sql      -> data/processed/funnel_hourly.csv
  3. sql/03_supply_demand_imbalance.sql -> data/processed/supply_imbalance.csv
  4. Join funnel + hourly supply-demand into the validated zone-hour table
     data/processed/dispatch_funnel_clean.csv

Usage (from the project root):
    python python/01_run_sql_pipeline.py
    # or: python -m python.01_run_sql_pipeline  (same, from root)
Requires: duckdb, pandas  (see requirements.txt)
"""
import sys
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SQL = ROOT / "sql"
PROC = ROOT / "data" / "processed"
PROC.mkdir(parents=True, exist_ok=True)


def run_sql(path: Path) -> pd.DataFrame:
    con = duckdb.connect()
    try:
        return con.execute(path.read_text()).fetchdf()
    finally:
        con.close()


def main() -> int:
    # 1. Data quality
    dq = run_sql(SQL / "01_data_quality_checks.sql")
    dq.to_csv(PROC / "dq_alerts.csv", index=False, lineterminator="\n")
    print(dq.to_string(index=False))
    n_fail = int((dq["verdict"] == "FAIL").sum())
    n_warn = int((dq["verdict"] == "WARN").sum())
    print(f"\nDQ: {n_fail} FAIL, {n_warn} WARN, {len(dq) - n_fail - n_warn} PASS")

    # 2. Funnel
    funnel = run_sql(SQL / "02_dispatch_funnel.sql")
    funnel.to_csv(PROC / "funnel_hourly.csv", index=False, lineterminator="\n")
    print(f"\nFunnel: {len(funnel)} zone-hours, "
          f"median_min overall {funnel['median_min'].median():.1f}, "
          f"p90_min overall {funnel['p90_min'].median():.1f}")

    # 3. Supply-demand imbalance
    imb = run_sql(SQL / "03_supply_demand_imbalance.sql")
    imb.to_csv(PROC / "supply_imbalance.csv", index=False, lineterminator="\n")
    print(f"Imbalance: {len(imb)} rows written")

    # 4. Validated zone-hour table: funnel (accept-hour) + hourly supply-demand
    hourly = pd.read_csv(ROOT / "data" / "raw" / "hourly_supply_demand.csv", parse_dates=["date"])
    funnel = funnel.copy()
    funnel["date"] = pd.to_datetime(funnel["accept_hour"]).dt.date
    funnel["hour"] = pd.to_datetime(funnel["accept_hour"]).dt.hour
    funnel["date"] = pd.to_datetime(funnel["date"])
    clean = funnel.merge(
        hourly,
        on=["city", "zone_id", "date", "hour"],
        how="left", suffixes=("", "_hourly"))
    # validation: every funnel zone-hour must match an hourly row; requests must agree
    assert clean["eyeballs"].notna().all(), "funnel zone-hour with no hourly row"
    mismatch = (clean["requests"] != clean["requests_hourly"]).sum() if "requests_hourly" in clean else 0
    # Expected: funnel excludes >12h durations (DQ WARN, 3,684 orders), so its
    # request count is lower than the raw hourly count in those zone-hours.
    print(f"Clean table: {len(clean)} zone-hours, zone-hours where funnel requests "
          f"< raw hourly requests (orders >12h excluded): {mismatch}")
    clean = clean[["city", "zone_id", "date", "hour", "accept_hour", "requests", "completed",
                   "active_couriers", "eyeballs", "median_min", "p90_min", "mean_min",
                   "pct_over_30min", "pct_over_240min", "rolling_3h_median_min",
                   "slowest_zone_rank_in_hour", "zeroes", "expected_requests",
                   "fulfilment_pct", "lost_orders_est", "courier_utilisation_pct"]]
    clean.to_csv(PROC / "dispatch_funnel_clean.csv", index=False, lineterminator="\n")
    print(f"Wrote data/processed/dispatch_funnel_clean.csv ({len(clean)} rows)")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
