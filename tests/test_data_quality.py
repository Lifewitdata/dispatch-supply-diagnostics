import numpy as np
import pandas as pd


def test_data_quality_verdicts(dq):
    verdicts = dq.set_index("check_name")["verdict"].to_dict()
    assert verdicts == {
        "duplicate_order_id": "PASS",
        "negative_accept_to_deliver_min": "PASS",
        "duration_over_12h": "WARN",
        "null_accept_gps": "PASS",
        "null_delivery_gps": "PASS",
        "null_zone_or_courier": "PASS",
        "delivery_before_accept_dt": "PASS",
        "date_ds_mismatch": "PASS",
    }
    assert len(dq) == 8
    assert dq["total_rows"].eq(304_286).all()


def test_data_quality_counts_match_source(events, dq):
    expected = {
        "duplicate_order_id": int(events.groupby("order_id").size().gt(1).sum()),
        "negative_accept_to_deliver_min": int(
            events["accept_to_deliver_min"].lt(0).sum()
        ),
        "duration_over_12h": int(events["accept_to_deliver_min"].gt(720).sum()),
        "null_accept_gps": int(
            events[["accept_gps_lng", "accept_gps_lat"]].isna().any(axis=1).sum()
        ),
        "null_delivery_gps": int(
            events[["delivery_gps_lng", "delivery_gps_lat"]].isna().any(axis=1).sum()
        ),
        "null_zone_or_courier": int(
            events[["zone_id", "courier_id"]].isna().any(axis=1).sum()
        ),
        "delivery_before_accept_dt": int(
            (
                pd.to_datetime(events["delivery_dt"])
                < pd.to_datetime(events["accept_dt"])
            ).sum()
        ),
        "date_ds_mismatch": int(
            (
                events["date"].str.replace("-", "", regex=False).astype(int)
                != 2022_0000 + events["ds"]
            ).sum()
        ),
    }
    actual = dq.set_index("check_name")["failed_rows"].to_dict()
    assert actual == expected
    assert actual["duration_over_12h"] == 3_684
    assert actual["null_accept_gps"] == 640
    expected_pct = pd.Series(expected) / len(events) * 100
    actual_pct = dq.set_index("check_name")["fail_pct"]
    np.testing.assert_allclose(
        actual_pct.to_numpy(), expected_pct.to_numpy(), atol=0.00001
    )
