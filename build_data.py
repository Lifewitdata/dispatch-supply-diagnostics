"""Build raw + hourly tables for dispatch-supply-diagnostics from LaDe-D.

Source: Cainiao-AI/LaDe-D on Hugging Face (CC BY-NC 4.0), 5 city parquets,
4,514,661 completed delivery tasks, 2022-05-01 to 2022-10-31 (ds = MMDD).
Sample used here (stated in README): 2022-06-01 to 2022-06-14, all 5 cities,
304,286 events. Full 4.5M rows are not shipped; the sample is reproducible
from the source parquets with the ds filter below.

Honest definitions (LaDe records ONLY completed deliveries):
- requests in a zone-hour = orders ACCEPTED in that hour (observed demand).
  Total demand including lost/unfulfilled orders is NOT in LaDe.
- completed in a zone-hour = orders DELIVERED in that hour.
- active_couriers = distinct couriers who accepted >=1 order in that zone-hour.
- eyeballs = distinct couriers ON SHIFT in that zone-hour: a courier is
  on shift in zone Z on day D from their first to their last accept in
  (Z, D). Eyeballs >= active_couriers; it is the supply the dispatcher
  could see, not a separate online/session feed (LaDe has none).
- zeroes = 1 when eyeballs == 0 in a zone-hour of the calendar grid.
- expected_requests = expanding median of requests for the same zone and
  hour-of-day over PRIOR days only (no leakage). First day has no baseline.
  fulfilment_pct = completed / expected_requests; lost_orders_est =
  max(0, expected_requests - completed). These are MODELLED estimates,
  not observed lost orders.
"""
import glob
import os
import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
SOURCE_DIR = Path(os.environ.get("LADE_SOURCE_DIR", ROOT / "data" / "source"))
RAW.mkdir(parents=True, exist_ok=True)
PROC.mkdir(parents=True, exist_ok=True)

START_DS, END_DS = 601, 614  # 2022-06-01 .. 2022-06-14

source_files = sorted(glob.glob(str(SOURCE_DIR / "*.parquet")))
if not source_files:
    raise FileNotFoundError(f"No LaDe-D parquet files found in {SOURCE_DIR}")

frames = []
for f in source_files:
    df = pd.read_parquet(f)
    df = df[(df["ds"] >= START_DS) & (df["ds"] <= END_DS)].copy()
    frames.append(df)
ev = pd.concat(frames, ignore_index=True)
print("events:", len(ev))

# Full dates: ds is MMDD, year 2022 (LaDe paper, Jun-Nov 2022 window; Jun sample)
ev["date"] = pd.to_datetime("2022-" + ev["ds"].astype(str).str.zfill(4).str[:2] + "-" + ev["ds"].astype(str).str.zfill(4).str[2:], format="%Y-%m-%d")
ev["accept_dt"] = pd.to_datetime(ev["date"].dt.strftime("%Y-%m-%d") + " " + ev["accept_time"].str[-8:], format="%Y-%m-%d %H:%M:%S")
ev["delivery_dt"] = pd.to_datetime(ev["date"].dt.strftime("%Y-%m-%d") + " " + ev["delivery_time"].str[-8:], format="%Y-%m-%d %H:%M:%S")
# accept_gps_time / delivery_gps_time are same-day times, same construction
ev["accept_gps_dt"] = pd.to_datetime(ev["date"].dt.strftime("%Y-%m-%d") + " " + ev["accept_gps_time"].str[-8:], format="%Y-%m-%d %H:%M:%S", errors="coerce")
ev["delivery_gps_dt"] = pd.to_datetime(ev["date"].dt.strftime("%Y-%m-%d") + " " + ev["delivery_gps_time"].str[-8:], format="%Y-%m-%d %H:%M:%S", errors="coerce")
# Deliveries can cross midnight: delivery clock time earlier than accept means next day.
_cross = ev["delivery_dt"] < ev["accept_dt"]
ev.loc[_cross, "delivery_dt"] = ev.loc[_cross, "delivery_dt"] + pd.Timedelta(days=1)
_cross_gps = ev["delivery_gps_dt"] < ev["accept_dt"]
ev.loc[_cross_gps, "delivery_gps_dt"] = ev.loc[_cross_gps, "delivery_gps_dt"] + pd.Timedelta(days=1)
ev["accept_to_deliver_min"] = (ev["delivery_dt"] - ev["accept_dt"]).dt.total_seconds() / 60.0
ev["zone_id"] = ev["region_id"]
ev = ev.sort_values(["date", "accept_dt", "order_id"]).reset_index(drop=True)

cols = ["order_id", "city", "zone_id", "region_id", "courier_id", "aoi_id", "aoi_type",
        "lng", "lat", "accept_gps_lng", "accept_gps_lat", "delivery_gps_lng", "delivery_gps_lat",
        "date", "accept_dt", "delivery_dt", "accept_gps_dt", "delivery_gps_dt",
        "accept_to_deliver_min", "ds", "accept_time", "delivery_time"]
ev[cols].to_csv(RAW / "lade_delivery_events.csv", index=False)
print("wrote lade_delivery_events.csv", ev.shape)
print(ev["accept_to_deliver_min"].describe())
print("negative durations:", int((ev["accept_to_deliver_min"] < 0).sum()),
      "| >12h:", int((ev["accept_to_deliver_min"] > 720).sum()),
      "| null accept GPS:", int(ev["accept_gps_lng"].isna().sum()),
      "| dup order_id:", int(ev["order_id"].duplicated().sum()))

# ---- hourly supply-demand grid ----
ev["accept_hour"] = ev["accept_dt"].dt.floor("h")
ev["delivery_hour"] = ev["delivery_dt"].dt.floor("h")
ev["hour"] = ev["accept_dt"].dt.hour

# on-shift (eyeballs): per courier-day-zone, shift = [min accept hour, max accept hour]
shifts = (ev.groupby(["city", "zone_id", "courier_id", "date"])["accept_hour"]
            .agg(["min", "max"]).reset_index()
            .rename(columns={"min": "shift_start", "max": "shift_end"}))

# calendar grid: every zone x date x hour 0-23 that appears in the sample
zones = ev[["city", "zone_id"]].drop_duplicates()
dates = pd.date_range("2022-06-01", "2022-06-14", freq="D")
grid = (zones.assign(_k=1).merge(pd.DataFrame({"date": dates, "_k": 1}), on="_k")
        .merge(pd.DataFrame({"hour": range(24), "_k": 1}), on="_k").drop(columns="_k"))
grid["hour_dt"] = grid["date"] + pd.to_timedelta(grid["hour"], unit="h")

req = ev.groupby(["city", "zone_id", "accept_hour"]).size().rename("requests").reset_index()
comp = ev.groupby(["city", "zone_id", "delivery_hour"]).size().rename("completed").reset_index()
act = ev.groupby(["city", "zone_id", "accept_hour"])["courier_id"].nunique().rename("active_couriers").reset_index()

hourly = grid.copy()
hourly = hourly.merge(req.rename(columns={"accept_hour": "hour_dt"}), on=["city", "zone_id", "hour_dt"], how="left")
hourly = hourly.merge(comp.rename(columns={"delivery_hour": "hour_dt"}), on=["city", "zone_id", "hour_dt"], how="left")
hourly = hourly.merge(act.rename(columns={"accept_hour": "hour_dt"}), on=["city", "zone_id", "hour_dt"], how="left")

# eyeballs: couriers whose shift covers this hour
shifts["shift_start_h"] = shifts["shift_start"].dt.hour
shifts["shift_end_h"] = shifts["shift_end"].dt.hour
eye_counts = {}
for (city, zone, date), g in shifts.groupby(["city", "zone_id", "date"]):
    for h in range(24):
        eye_counts[(city, zone, date, h)] = int(((g["shift_start_h"] <= h) & (g["shift_end_h"] >= h)).sum())
hourly["eyeballs"] = [eye_counts.get((r.city, r.zone_id, r.date, r.hour), 0) for r in hourly.itertuples()]

hourly[["requests", "completed", "active_couriers"]] = hourly[["requests", "completed", "active_couriers"]].fillna(0).astype(int)
hourly["zeroes"] = (hourly["eyeballs"] == 0).astype(int)
hourly["courier_utilisation_pct"] = np.where(hourly["eyeballs"] > 0, hourly["active_couriers"] / hourly["eyeballs"] * 100, np.nan)

# expected requests: expanding median of prior days, same zone + hour-of-day.
# Fulfilment / lost are measured on ACCEPTS (requests), not deliveries:
# completed in an hour lags accepts by a ~2h median duration, so comparing
# completed to expected_requests in the same hour would invent lost orders.
# lost_orders_est = shortfall in accepts vs the zone's own normal demand
# for that hour -- the signature of thin/zero supply.
hourly = hourly.sort_values(["city", "zone_id", "hour", "date"])
hourly["expected_requests"] = hourly.groupby(["city", "zone_id", "hour"])["requests"].transform(
    lambda s: s.expanding().median().shift(1))
hourly["fulfilment_pct"] = np.where(hourly["expected_requests"] > 0,
                                    hourly["requests"] / hourly["expected_requests"] * 100, np.nan)
# Lost orders: ONLY in supply-constrained hours (eyeballs <= 1). Counting every
# below-median hour as lost would invent ~150k lost orders from ordinary
# day-to-day variance (one-sided clipping bias). In a zero/thin-supply hour
# accepts are 0 by construction, so lost = the zone's normal demand there.
hourly["lost_orders_est"] = np.where(
    (hourly["expected_requests"].notna()) & (hourly["eyeballs"] <= 1),
    (hourly["expected_requests"] - hourly["requests"]).clip(lower=0), 0.0)

out = hourly[["city", "zone_id", "date", "hour", "eyeballs", "active_couriers", "requests",
              "completed", "zeroes", "expected_requests", "fulfilment_pct", "lost_orders_est",
              "courier_utilisation_pct"]]
out.to_csv(RAW / "hourly_supply_demand.csv", index=False)
print("wrote hourly_supply_demand.csv", out.shape)
print("zero-supply zone-hours:", int(out["zeroes"].sum()), "/", len(out), f"({out['zeroes'].mean()*100:.1f}%)")
print("total requests:", int(out["requests"].sum()), "completed:", int(out["completed"].sum()))
print("lost_orders_est total (days 2-14):", round(float(out["lost_orders_est"].sum(skipna=True)), 1))
