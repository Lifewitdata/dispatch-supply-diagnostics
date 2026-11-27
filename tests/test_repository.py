import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_repository_scaffolding_protects_data_and_configures_deployment():
    assert (ROOT / "LICENSE").is_file()
    assert (ROOT / ".github" / "workflows" / "ci.yml").is_file()
    assert (ROOT / "dashboard" / "dispatch_supply_health.py").is_file()

    ignored = [
        ".venv/bin/python",
        "__pycache__/module.pyc",
        ".pytest_cache/README.md",
        ".streamlit/secrets.toml",
        "data/source/city.parquet",
    ]
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", *ignored],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert set(result.stdout.splitlines()) == set(ignored)

    required = [
        "data/raw/lade_delivery_events.csv",
        "data/raw/hourly_supply_demand.csv",
        "data/processed/dispatch_funnel_clean.csv",
        ".streamlit/config.toml",
    ]
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", *required],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert not result.stdout.strip()

    config = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text())
    assert config["server"]["headless"] is True
    assert config["browser"]["gatherUsageStats"] is False
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "python -m pytest -q" in workflow
    assert "python python/01_run_sql_pipeline.py" in workflow
