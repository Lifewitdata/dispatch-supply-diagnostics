import importlib.util
import os
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location(
    "sql_pipeline", ROOT / "python" / "01_run_sql_pipeline.py"
)
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)


@pytest.fixture(scope="session", autouse=True)
def project_working_directory():
    previous = Path.cwd()
    os.chdir(ROOT)
    try:
        yield
    finally:
        os.chdir(previous)


@pytest.fixture(scope="session")
def sql_pipeline():
    return pipeline


@pytest.fixture(scope="session")
def events():
    return pd.read_csv(
        ROOT / "data" / "raw" / "lade_delivery_events.csv",
        usecols=[
            "order_id",
            "city",
            "zone_id",
            "date",
            "accept_dt",
            "delivery_dt",
            "ds",
            "courier_id",
            "accept_gps_lng",
            "accept_gps_lat",
            "delivery_gps_lng",
            "delivery_gps_lat",
            "accept_to_deliver_min",
        ],
    )


@pytest.fixture(scope="session")
def hourly():
    return pd.read_csv(
        ROOT / "data" / "raw" / "hourly_supply_demand.csv", parse_dates=["date"]
    )


@pytest.fixture(scope="session")
def clean():
    return pd.read_csv(
        ROOT / "data" / "processed" / "dispatch_funnel_clean.csv",
        parse_dates=["date", "accept_hour"],
    )


@pytest.fixture(scope="session")
def dq(sql_pipeline):
    return sql_pipeline.run_sql(ROOT / "sql" / "01_data_quality_checks.sql")


@pytest.fixture(scope="session")
def funnel(sql_pipeline):
    return sql_pipeline.run_sql(ROOT / "sql" / "02_dispatch_funnel.sql")


@pytest.fixture(scope="session")
def imbalance(sql_pipeline):
    return sql_pipeline.run_sql(ROOT / "sql" / "03_supply_demand_imbalance.sql")
