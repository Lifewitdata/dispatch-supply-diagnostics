"""Dispatch & Supply Health dashboard (Streamlit).

Run from the project root:
    streamlit run dashboard/dispatch_supply_health.py
Data: data/processed/dispatch_funnel_clean.csv (17,784 zone-hours) and
data/raw/hourly_supply_demand.csv (54,432 zone-hours, full grid).
Source: Cainiao LaDe-D, 2022-06-01 to 2022-06-14, 304,286 tasks, 5 cities.
Lost orders are MODELLED (see README), not observed.
"""
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]

st.set_page_config(page_title="Dispatch & Supply Health — LaDe-D", layout="wide")
st.title("Dispatch & Supply Health")
st.caption("Cainiao LaDe-D  •  2022-06-01 to 2022-06-14  •  304,286 completed tasks  •  5 cities  •  "
           "Lost orders are modelled, not observed — see README.")


@st.cache_data
def load():
    clean = pd.read_csv(ROOT / "data/processed/dispatch_funnel_clean.csv",
                        parse_dates=["date", "accept_hour"])
    hourly = pd.read_csv(ROOT / "data/raw/hourly_supply_demand.csv", parse_dates=["date"])
    return clean, hourly


clean, hourly = load()
cities = st.sidebar.multiselect("City", sorted(clean["city"].unique()),
                                default=sorted(clean["city"].unique()))
c = clean[clean["city"].isin(cities)]
h = hourly[hourly["city"].isin(cities)]
if c.empty:
    st.warning("Select at least one city.")
    st.stop()

# KPIs (event-level medians are from the raw file; zone-hour medians here are
# medians of hourly medians — see README for the difference)
k1, k2, k3, k4 = st.columns(4)
k1.metric("Tasks (accepts)", f"{int(h['requests'].sum()):,}")  # raw hourly total, not funnel (which excludes >12h)
k2.metric("Zone-hour median (median)", f"{c['median_min'].median():.0f} min")
k3.metric("Zone-hour p90 (median)", f"{c['p90_min'].median():.0f} min")
peak = h[(h["hour"] >= 7) & (h["hour"] <= 22)]
k4.metric("Peak zero-supply rate", f"{peak['zeroes'].mean() * 100:.1f}%")
st.metric("Modelled lost orders / day", f"{h['lost_orders_est'].sum() / 14:,.0f}",
          help="Modelled only, in hours with <=1 courier on shift. Not observed lost orders.")

tab1, tab2, tab3 = st.tabs(["Speed", "Supply & lost orders", "Sizing"])

with tab1:
    st.subheader("Median duration by city (zone-hour medians)")
    st.bar_chart(c.groupby("city")["median_min"].median())
    st.subheader("Requests by hour of day")
    st.bar_chart(h.groupby("hour")["requests"].sum())
    st.subheader("Load vs speed — median duration by requests per courier")
    cc = c.copy()
    cc["load"] = cc["requests"] / cc["active_couriers"]
    cc["load_bin"] = pd.cut(cc["load"], [0, 1, 2, 3, 5, 10, 100],
                            labels=["<=1", "1-2", "2-3", "3-5", "5-10", ">10"])
    st.bar_chart(cc.groupby("load_bin", observed=True)["median_min"].median())
    st.caption("Median 35 min at load <=1, 66 min at load 2-3, 108 min at load 5-10, "
               "146 min at load >10. Association, not causal (R2 0.14 in the notebook).")

with tab2:
    st.subheader("Zero-supply rate by hour")
    st.bar_chart((h.groupby("hour")["zeroes"].mean() * 100).round(1))
    st.subheader("Worst zones by modelled lost orders (14 days)")
    worst = (h.groupby(["city", "zone_id"])["lost_orders_est"].sum()
               .sort_values(ascending=False).head(15).reset_index())
    st.dataframe(worst, use_container_width=True)
    st.subheader("Supply imbalance by city")
    st.dataframe(pd.read_csv(ROOT / "data/processed/supply_imbalance.csv")
                 .query("grain == 'by_city'"), use_container_width=True)

with tab3:
    st.subheader("Sizing calculator — speed vs cost")
    st.caption("Assumed courier cost (LaDe has no pay data). Extra courier-hours "
               "are computed live from the zone-hour table.")
    target = st.slider("Target load (requests per active courier)", 2, 5, 3)
    rate = st.slider("Courier cost (CNY / hour)", 20, 40, 30)
    extra = (c["requests"] / target - c["active_couriers"]).clip(lower=0)
    st.metric("Extra courier-hours / day", f"{extra.sum() / 14:,.0f}")
    st.metric("Cost / day", f"CNY {extra.sum() / 14 * rate:,.0f}")
    st.metric("Zone-hours affected", f"{int((extra > 0).sum()):,}")
    st.caption("Covering every zero-supply peak zone-hour (07:00-22:00) with 1 courier "
               f"needs {peak['zeroes'].sum() / 14:,.0f} courier-hours/day "
               f"(CNY {peak['zeroes'].sum() / 14 * rate:,.0f}/day at CNY {rate}/h) "
               f"against {peak['lost_orders_est'].sum() / 14:,.0f} modelled lost orders/day.")
