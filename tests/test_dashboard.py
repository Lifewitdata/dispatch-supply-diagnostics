from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "dashboard" / "dispatch_supply_health.py"


def test_dashboard_loads_expected_metrics_and_tabs():
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not app.exception
    assert app.title[0].value == "Dispatch & Supply Health"
    labels = [metric.label for metric in app.metric]
    values = [metric.value for metric in app.metric]
    assert "Tasks (accepts)" in labels
    assert "Peak zero-supply rate" in labels
    assert "304,286" in values
    assert "37.7%" in values
    assert [tab.label for tab in app.tabs] == ["Speed", "Supply & lost orders", "Sizing"]
    app.slider[0].set_value(5).run()
    app.slider[1].set_value(40).run()
    values = [metric.value for metric in app.metric]
    assert "1,571" in values
    assert "CNY 62,857" in values
    assert "5,465" in values


def test_dashboard_handles_city_filter_and_empty_selection():
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    app.multiselect[0].set_value(["Hangzhou"]).run()
    assert not app.exception
    assert "137,459" in [metric.value for metric in app.metric]
    app.multiselect[0].set_value([]).run()
    assert not app.exception
    assert any("Select at least one city" in warning.value for warning in app.warning)
