import duckdb
import numpy as np
import pandas as pd
import pytest


def test_pipeline_writes_all_outputs(sql_pipeline, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(sql_pipeline, "PROC", tmp_path)
    assert sql_pipeline.main() == 0
    assert {path.name for path in tmp_path.glob("*.csv")} == {
        "dq_alerts.csv",
        "funnel_hourly.csv",
        "supply_imbalance.csv",
        "dispatch_funnel_clean.csv",
    }
    clean = pd.read_csv(tmp_path / "dispatch_funnel_clean.csv")
    assert len(clean) == 17_784
    assert "DQ: 0 FAIL, 1 WARN, 7 PASS" in capsys.readouterr().out


def test_funnel_has_one_row_per_valid_zone_hour(funnel, events):
    keys = ["city", "zone_id", "accept_hour"]
    valid = events["accept_to_deliver_min"].between(0, 720)
    source = events.loc[valid, ["city", "zone_id", "accept_dt"]].copy()
    source["accept_hour"] = pd.to_datetime(source["accept_dt"]).dt.floor("h")
    expected = pd.MultiIndex.from_frame(source[keys]).unique()
    actual = pd.MultiIndex.from_frame(funnel[keys])
    assert len(funnel) == 17_784
    assert not funnel.duplicated(keys).any()
    assert len(actual) == len(expected)
    assert actual.difference(expected).empty
    assert expected.difference(actual).empty
    assert funnel["city"].nunique() == 5


def test_funnel_counts_exclude_only_long_durations(funnel, events):
    valid = events["accept_to_deliver_min"].between(0, 720)
    assert int(funnel["requests"].sum()) == int(valid.sum())
    assert int((~valid).sum()) == 3_684
    assert funnel["requests"].sum() + (~valid).sum() == len(events)


def test_funnel_duration_metrics_are_ordered_and_bounded(funnel):
    assert funnel["median_min"].between(0, 720).all()
    assert (funnel["median_min"] <= funnel["p90_min"]).all()
    assert (funnel["mean_min"] <= 720).all()
    assert funnel["pct_over_30min"].between(0, 100).all()
    assert funnel["pct_over_240min"].between(0, 100).all()
    assert funnel["active_couriers"].ge(1).all()


def test_rolling_median_uses_three_observed_rows(funnel):
    for _, group in funnel.sort_values("accept_hour").groupby(["city", "zone_id"]):
        expected = group["median_min"].rolling(3, min_periods=1).median().round(1)
        actual = group["rolling_3h_median_min"].reset_index(drop=True)
        np.testing.assert_allclose(
            actual.to_numpy(), expected.to_numpy(), atol=0.11, equal_nan=True
        )


def test_slowest_zone_rank_matches_hourly_p90(funnel):
    keys = ["city", "zone_id", "accept_hour"]
    with duckdb.connect() as connection:
        p90 = connection.execute(
            """
            SELECT city, zone_id, date_trunc('hour', accept_dt) AS accept_hour,
                   round(quantile_cont(accept_to_deliver_min, 0.9), 1) AS p90_min
            FROM read_csv('data/raw/lade_delivery_events.csv', header = true)
            WHERE accept_to_deliver_min BETWEEN 0 AND 720
            GROUP BY city, zone_id, accept_hour
            """
        ).fetchdf()
    p90 = p90.set_index(keys)["p90_min"]
    expected = p90.groupby(level="accept_hour").rank(
        method="min", ascending=False
    )
    actual = funnel.set_index(keys)["slowest_zone_rank_in_hour"]
    pd.testing.assert_series_equal(
        actual.sort_index(),
        expected.sort_index().astype("int64"),
        check_names=False,
        check_dtype=False,
    )


def test_imbalance_city_totals_reconcile_to_hourly_grid(imbalance, hourly):
    cities = imbalance.loc[imbalance["grain"] == "by_city"]
    assert len(cities) == 5
    assert cities["zone_hours"].sum() == len(hourly) == 54_432
    assert cities["requests"].sum() == hourly["requests"].sum() == 304_286
    assert cities["completed"].sum() == hourly["completed"].sum() == 304_181
    assert cities["lost_orders_est"].sum() == pytest.approx(
        hourly["lost_orders_est"].sum(), abs=0.1
    )


def test_imbalance_contains_every_hour_band_and_worst_zones(imbalance):
    bands = imbalance.loc[imbalance["grain"] == "by_city_hour_band"]
    worst = imbalance.loc[imbalance["grain"] == "worst_zones"]
    assert len(bands) == 5 * 5
    assert bands.groupby("group_1")["group_2"].nunique().eq(5).all()
    band_keys = bands[["group_1", "group_2"]].apply(tuple, axis=1)
    assert band_keys.is_monotonic_increasing
    assert len(worst) == 15
    assert worst["lost_orders_est"].is_monotonic_decreasing
    assert worst["group_1"].notna().all()
    assert worst["group_2"].notna().all()


def test_clean_table_preserves_funnel_and_supply_join(clean, funnel, hourly, events):
    assert len(clean) == len(funnel)
    keys = ["city", "zone_id", "date", "hour"]
    hourly_keys = pd.MultiIndex.from_frame(hourly[keys])
    clean_keys = pd.MultiIndex.from_frame(clean[keys])
    assert clean_keys.isin(hourly_keys).all()
    assert clean["eyeballs"].notna().all()
    assert clean["zeroes"].isin([0, 1]).all()
    joined = clean.merge(
        hourly[keys + ["requests"]].rename(columns={"requests": "hourly_requests"}),
        on=keys,
        how="left",
        validate="one_to_one",
    )
    assert joined["requests"].le(joined["hourly_requests"]).all()
    valid = events["accept_to_deliver_min"].between(0, 720)
    source = events.copy()
    source["accept_hour"] = pd.to_datetime(source["accept_dt"]).dt.floor("h")
    keys = ["city", "zone_id", "accept_hour"]
    all_counts = source.groupby(keys).size()
    valid_counts = source.loc[valid].groupby(keys).size()
    omitted_hours = all_counts.loc[~all_counts.index.isin(valid_counts.index)]
    assert not omitted_hours.empty
    assert omitted_hours.sum() + (
        joined["hourly_requests"] - joined["requests"]
    ).sum() == (~valid).sum()


def test_hourly_baseline_and_losses_use_prior_days_only(hourly):
    for _, group in hourly.sort_values("date").groupby(["city", "zone_id", "hour"]):
        expected = group["requests"].expanding().median().shift(1)
        np.testing.assert_allclose(
            group["expected_requests"], expected, equal_nan=True, atol=0.00001
        )
        thin_supply = group["eyeballs"].le(1) & expected.notna()
        expected_lost = (expected - group["requests"]).clip(lower=0).where(
            thin_supply, 0.0
        )
        np.testing.assert_allclose(
            group["lost_orders_est"], expected_lost, atol=0.00001
        )
