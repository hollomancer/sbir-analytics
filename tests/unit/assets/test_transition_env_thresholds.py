"""A mistyped transition quality-gate threshold must stop the check, not be ignored."""

import json

import pandas as pd
import pytest
from dagster import build_asset_context

from sbir_analytics.assets.transition.checks import contracts_sample_quality_check
from sbir_analytics.assets.transition.evidence import transformed_transition_evidence


pytestmark = pytest.mark.unit


def _sample() -> pd.DataFrame:
    return pd.DataFrame({"action_date": ["2024-01-01"], "vendor_uei": ["ABC123DEF456"]})


@pytest.mark.parametrize(
    ("key", "raw"),
    [
        ("SBIR_ETL__TRANSITION__CONTRACTS__DATE_COVERAGE_MIN", "0,8"),
        ("SBIR_ETL__TRANSITION__CONTRACTS__DATE_COVERAGE_MIN", "abc"),
        ("SBIR_ETL__TRANSITION__CONTRACTS__SAMPLE_SIZE_MIN", "1e3"),
    ],
)
def test_contracts_sample_check_raises_on_bad_threshold(monkeypatch, key, raw):
    monkeypatch.setenv(key, raw)
    with pytest.raises(ValueError, match=key):
        contracts_sample_quality_check(_sample())


def test_contracts_sample_check_uses_valid_threshold(monkeypatch):
    monkeypatch.setenv("SBIR_ETL__TRANSITION__CONTRACTS__DATE_COVERAGE_MIN", " 0.5 ")
    result = contracts_sample_quality_check(_sample())
    assert result.metadata["thresholds"].value["action_date_min"] == "50.00%"


def test_evidence_validation_summary_raises_on_bad_threshold(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    checks = tmp_path / "data/processed/contracts_sample.checks.json"
    checks.parent.mkdir(parents=True)
    checks.write_text(json.dumps({"coverage": {"action_date": 1.0, "any_identifier": 1.0}}))
    key = "SBIR_ETL__TRANSITION__CONTRACTS__DATE_COVERAGE_MIN"
    monkeypatch.setenv(key, "0,8")
    scores = pd.DataFrame(
        {"award_id": ["A1"], "contract_id": ["C1"], "score": [0.9], "method": ["uei"]}
    )
    contracts = pd.DataFrame({"contract_id": ["C1"], "action_date": ["2024-01-01"]})
    with pytest.raises(ValueError, match=key):
        transformed_transition_evidence(build_asset_context(), scores, contracts)
