"""The CI analytics gate must reject a mistyped minimum rate, not ignore it."""

import json

import pytest

from scripts.ci import gate_check


pytestmark = pytest.mark.unit


def _write_analytics_checks(tmp_path):
    path = tmp_path / "data/processed/transition_analytics.checks.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "award_transition_rate": {"denominator": 10, "rate": 0.5},
                "company_transition_rate": {"denominator": 5, "rate": 0.4},
            }
        )
    )


@pytest.mark.parametrize(
    "key",
    [
        "SBIR_ETL__TRANSITION__ANALYTICS__MIN_AWARD_RATE",
        "SBIR_ETL__TRANSITION__ANALYTICS__MIN_COMPANY_RATE",
    ],
)
def test_analytics_gate_raises_on_bad_min_rate(monkeypatch, tmp_path, key):
    monkeypatch.chdir(tmp_path)
    _write_analytics_checks(tmp_path)
    monkeypatch.setenv(key, "0,9")
    with pytest.raises(ValueError, match=key):
        gate_check.gate_transition_analytics()


def test_analytics_gate_applies_valid_min_rate(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _write_analytics_checks(tmp_path)
    monkeypatch.setenv("SBIR_ETL__TRANSITION__ANALYTICS__MIN_AWARD_RATE", "0.6")
    assert gate_check.gate_transition_analytics() == 1
