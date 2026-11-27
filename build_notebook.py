"""Generate python/02_root_cause_and_sizing.ipynb (executed by nbconvert)."""
from pathlib import Path

import nbformat as nbf

OUTPUT = Path(__file__).resolve().parent / "python" / "02_root_cause_and_sizing.ipynb"

nb = nbf.v4.new_notebook()
cells = []


def md(s):
    cells.append(nbf.v4.new_markdown_cell(s.strip()))


def code(s):
    cells.append(nbf.v4.new_code_cell(s.strip()))


md("""# Dispatch & Supply Diagnostics — root cause and sizing
**Source:** Cainiao LaDe-D (Hugging Face `Cainiao-AI/LaDe-D`, CC BY-NC 4.0),
5 Chinese cities, sample **2022-06-01 to 2022-06-14, 304,286 completed
delivery tasks**. LaDe records only completed deliveries — total demand
including lost orders is NOT observed. Lost orders here are *modelled*:
shortfall in accepts vs a zone's own prior-days median, counted only in
hours with <=1 courier on shift (eyeballs). See README for definitions.
**Question:** why are some zones slow, where are orders lost, and how many
courier-hours would it cost to fix it?""")

code("""from pathlib import Path
import pandas as pd, numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
%matplotlib inline
pd.set_option('display.max_columns', 20)
PROJECT_ROOT = Path.cwd().parent if (Path.cwd().parent / 'data').is_dir() else Path.cwd()
ev = pd.read_csv(PROJECT_ROOT / 'data/raw/lade_delivery_events.csv', parse_dates=['date','accept_dt','delivery_dt'])
h = pd.read_csv(PROJECT_ROOT / 'data/raw/hourly_supply_demand.csv', parse_dates=['date'])
c = pd.read_csv(PROJECT_ROOT / 'data/processed/dispatch_funnel_clean.csv', parse_dates=['date','accept_hour'])
dq = pd.read_csv(PROJECT_ROOT / 'data/processed/dq_alerts.csv')
print('events', len(ev), '| zone-hours (clean)', len(c), '| hourly grid', len(h))
print(dq.to_string(index=False))""")

md("""## 1. Funnel — how slow is accept-to-deliver?
Duration is accept-to-deliver in minutes (courier accepts a task, then
delivers it). Durations over 12h (3,684 orders, 1.2%) are flagged in DQ
and excluded from speed percentiles, not deleted.""")

code("""print(ev['accept_to_deliver_min'].describe().round(1))
print('\\nBy city (event level):')
print(ev.groupby('city')['accept_to_deliver_min'].agg(['count','median',lambda s: s.quantile(0.9)]).round(1))
print('\\nBy hour band (accept hour):')
ev['hour'] = ev['accept_dt'].dt.hour
ev['band'] = pd.cut(ev['hour'], [-1,5,11,16,22,23], labels=['night 0-5','morning 6-11','afternoon 12-16','evening 17-22','late 23'])
print(ev.groupby('band', observed=True)['accept_to_deliver_min'].agg(['count','median',lambda s: s.quantile(0.9)]).round(1))""")

code("""fig, ax = plt.subplots(1, 2, figsize=(12, 4))
ev.groupby('city')['accept_to_deliver_min'].median().sort_values().plot.barh(ax=ax[0], color='steelblue')
ax[0].set_title('Median accept-to-deliver (min) by city'); ax[0].set_xlabel('minutes')
ev.groupby('hour')['accept_to_deliver_min'].median().plot(ax=ax[1], marker='o')
ax[1].set_title('Median duration by accept hour'); ax[1].set_xlabel('hour'); ax[1].set_ylabel('minutes')
plt.tight_layout(); plt.show()""")

md("""## 2. Root cause 1 — load: requests per active courier
At zone-hour level, load = requests / active couriers. Median duration
rises monotonically with load. This is the strongest operational driver
found (see OLS below).""")

code("""c['load'] = c['requests'] / c['active_couriers']
c['load_bin'] = pd.cut(c['load'], [0,1,2,3,5,10,100], labels=['<=1','1-2','2-3','3-5','5-10','>10'])
print(c.groupby('load_bin', observed=True).agg(zone_hours=('median_min','count'), orders=('requests','sum'), median_min=('median_min','median'), p90_min=('p90_min','median')).round(1))
print('\\ncorr(load, zone-hour median):', round(c[['load','median_min']].corr().iloc[0,1], 3))
print('corr(requests, zone-hour median):', round(c[['requests','median_min']].corr().iloc[0,1], 3))
print('corr(eyeballs, zone-hour median):', round(c[['eyeballs','median_min']].corr().iloc[0,1], 3))""")

code("""import statsmodels.api as sm
d = c.dropna(subset=['load','median_min']).copy()
X = pd.get_dummies(d[['load','city']], columns=['city'], drop_first=True, dtype=float)
X = sm.add_constant(X)
m = sm.OLS(d['median_min'], X).fit()
print(m.summary().tables[1])
print('R2 =', round(m.rsquared, 3))
print('\\nReading: each extra order per courier in a zone-hour adds ~5 min to the')
print('hourly median, holding city constant. City effects are large: Hangzhou')
print('and Shanghai are structurally ~50-70 min faster than Chongqing at the')
print('same load. R2 is only 0.14 — load matters, but it is not the whole story.')""")

md("""## 3. Root cause 2 — zero / thin supply and lost orders
Zeroes are read from the full zone-hour grid (`hourly_supply_demand.csv`),
not from the funnel table (which only has hours with at least one order).
Lost orders are modelled, only in hours with <=1 courier on shift.""")

code("""print('Zero-supply zone-hours:', int(h['zeroes'].sum()), '/', len(h), f"({h['zeroes'].mean()*100:.1f}%)")
print('Peak hours 07-22 zeroes:', f"{h[(h['hour']>=7)&(h['hour']<=22)]['zeroes'].mean()*100:.1f}%")
print('\\nZeroes by hour band:')
h['band'] = pd.cut(h['hour'], [-1,5,11,16,22,23], labels=['night 0-5','morning 6-11','afternoon 12-16','evening 17-22','late 23'])
print((h.groupby('band', observed=True)['zeroes'].mean()*100).round(1))
print('\\nModelled lost orders (14 days):', round(h['lost_orders_est'].sum(), 1), '=', round(h['lost_orders_est'].sum()/14, 1), 'per day')
print(h.groupby('city')['lost_orders_est'].sum().sort_values(ascending=False).round(1))
print('\\nWorst zones by modelled lost orders:')
print(h.groupby(['city','zone_id'])['lost_orders_est'].sum().sort_values(ascending=False).head(10).round(1))""")

code("""fig, ax = plt.subplots(1, 2, figsize=(12, 4))
(h.groupby('hour')['requests'].sum()).plot(ax=ax[0], marker='o')
ax[0].set_title('Requests (accepts) by hour of day'); ax[0].set_xlabel('hour')
(h.groupby('hour')['zeroes'].mean()*100).plot(ax=ax[1], marker='o', color='crimson')
ax[1].set_title('Zero-supply rate (%) by hour'); ax[1].set_xlabel('hour')
plt.tight_layout(); plt.show()""")

md("""## 4. Sizing — speed vs cost
Two interventions, costed at an **assumed** courier cost of CNY 30/hour
(LaDe has no pay data; sensitivity at CNY 20 / 40 is shown). Costs are
courier-hours, not a promise that every modelled lost order is recovered.
**A — cover zero-supply peak hours:** 1 courier in every zero-supply
zone-hour, 07:00-22:00. **B — cut load in busy hours:** add couriers until
load <= 3 (or <= 5) in every zone-hour above that load.""")

code("""peak = h[(h['hour']>=7)&(h['hour']<=22)]
zero_hours_day = peak['zeroes'].sum()/14
print(f"A: zero peak zone-hours per day: {zero_hours_day:.0f} courier-hours/day")
for rate in [20, 30, 40]:
    print(f"   cost/day at CNY {rate}/h: CNY {zero_hours_day*rate:,.0f}")
print(f"   modelled lost orders in peak hours: {peak['lost_orders_est'].sum()/14:.0f}/day")
print(f"   cost per modelled lost order if all were recovered: CNY {zero_hours_day*30/(peak['lost_orders_est'].sum()/14):.0f} (upper bound, recovery is not 1:1)")
print()
for target in [5, 3, 2]:
    extra = (c['requests']/target - c['active_couriers']).clip(lower=0)
    print(f"B: target load <={target}: +{extra.sum()/14:.0f} courier-hours/day, "
          f"CNY {extra.sum()/14*30:,.0f}/day at CNY 30/h "
          f"(CNY {extra.sum()/14*20:,.0f} at 20, CNY {extra.sum()/14*40:,.0f} at 40), "
          f"{int((extra>0).sum())} zone-hours affected")
print()
print('Expected speed gain (binned association, not causal): zone-hours at load')
print('>5 have median 108-146 min; at load 3-5 the median is 78.5 min, at')
print('load 2-3 it is 66 min. So intervention B moves busy hours toward')
print('~66-79 min median, from ~108-146 min.')""")

md("""## 5. Recommendation
1. **Start with A, in Hangzhou and Chongqing.** Hangzhou loses the most
modelled orders (635/day) and Chongqing is next (362/day); the worst
single zones are Hangzhou 60 (902 modelled lost in 14 days) and
Hangzhou 96 (497). Staffing 1 courier per zero peak zone-hour costs
~CNY 29k/day at the assumed rate.
2. **Then B in the morning peak (06:00-11:00).** Morning is the slowest
band (median 151 min) and the biggest volume (146,365 orders, 08:00
alone is 58,888). Cutting load to <=3 costs ~CNY 117k/day — do it only
in the worst morning zones first, not everywhere.
3. **Do not build a policy on the 23:00 band.** Only 169 orders, median
5 min — a small-n artefact, not a real fast hour.
## Limitations — do not overclaim
- LaDe records completed deliveries only; lost orders are modelled, not observed.
- Eyeballs are a derived on-shift proxy (first-to-last accept in a zone-day);
LaDe has no online/session feed.
- Duration is accept-to-deliver, not pure travel time; it includes waiting
and batching at the station.
- The load-duration link is an association (R2 0.14); the sizing is a
scenario, not a causal estimate. Courier cost CNY 30/h is an assumption.
- Sample is 14 days in June 2022, 5 Chinese cities; do not generalise to
other seasons, cities, or platforms (e.g. Mrsool / Saudi).""")

nb.cells = cells
nbf.write(nb, OUTPUT)
print("wrote notebook, cells:", len(cells))
