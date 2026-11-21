"""A mistyped transition quality-gate threshold must stop the check, not be ignored."""

import pandas as pd
import pytest

from sbir_analytics.assets.transition.checks import contracts_sample_quality_check


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
