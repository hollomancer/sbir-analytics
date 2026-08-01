"""Required inputs of the monthly procurement packet scripts fail closed."""

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_script(name: str):
    path = REPO_ROOT / "scripts" / "data" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "script", ["monthly_procurement_transition_report", "enrich_procurement_awards"]
)
def test_missing_required_input_raises(tmp_path, script):
    module = _load_script(script)
    # A typo or a missing upstream artifact must not exit zero with a plausible
    # zero-lead packet.
    with pytest.raises(FileNotFoundError):
        module._read(tmp_path / "absent.parquet", required=True)


@pytest.mark.parametrize(
    "script", ["monthly_procurement_transition_report", "enrich_procurement_awards"]
)
def test_optional_previous_snapshot_still_degrades_to_empty(tmp_path, script):
    module = _load_script(script)
    assert module._read(None).empty
    assert module._read(tmp_path / "absent.parquet").empty


def test_present_required_input_is_read(tmp_path):
    module = _load_script("monthly_procurement_transition_report")
    path = tmp_path / "awards.csv"
    pd.DataFrame([{"award_id": "A-1"}]).to_csv(path, index=False)
    assert len(module._read(path, required=True)) == 1
