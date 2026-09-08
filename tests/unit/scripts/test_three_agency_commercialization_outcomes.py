import importlib.util
import sys
from datetime import date
from pathlib import Path

import pandas as pd


SCRIPT = Path(__file__).resolve().parents[3] / "scripts/data/three_agency_commercialization_outcomes.py"
SPEC = importlib.util.spec_from_file_location("three_agency_commercialization_outcomes", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_agency_scope_is_exact():
    assert MODULE.agency_label(pd.Series({"Agency": "National Aeronautics and Space Administration"})) == "NASA"
    assert MODULE.agency_label(pd.Series({"Agency": "Department of Energy", "Branch": "ARPA-E"})) == "DOE"
    assert MODULE.agency_label(pd.Series({"Agency": "Department of Defense", "Branch": "Air Force"})) == "Air Force"
    assert MODULE.agency_label(pd.Series({"Agency": "Department of Defense", "Branch": "Space Development Agency"})) is None


def test_phase_i_ii_research_exclusion_retains_phase_iii():
    assert MODULE.is_phase_i_ii_research("SR1")
    assert MODULE.is_phase_i_ii_research("SMALL BUSINESS INNOVATION RESEARCH PROGRAM PHASE II ACTION")
    assert not MODULE.is_phase_i_ii_research("SR3")
    assert not MODULE.is_phase_i_ii_research(None)


def test_form_d_amendment_series_key_uses_first_sale_and_security_type():
    original = {
        "cik": "000123",
        "date_of_first_sale": "2018-04-01",
        "securities_types": ["options", "equity"],
    }
    amendment = {
        "cik": "123",
        "date_of_first_sale": "2018-04-01",
        "securities_types": ["equity", "options"],
        "is_amendment": True,
    }
    assert MODULE.offering_series_key(original) == MODULE.offering_series_key(amendment)


def test_channel_summary_enforces_anchor_and_horizon():
    eligible = pd.DataFrame(
        [{"firm_id": "uei:A", "anchor_date": date(2015, 1, 1), "phase_ii_dollars": 1_000_000}]
    )
    events = pd.DataFrame(
        [
            {"firm_id": "uei:A", "event_date": date(2014, 1, 1), "amount": 99.0},
            {"firm_id": "uei:A", "event_date": date(2017, 1, 1), "amount": 500_000.0},
            {"firm_id": "uei:A", "event_date": date(2021, 1, 1), "amount": 999.0},
        ]
    )
    summary, firms = MODULE.summarize_channel(
        eligible,
        events,
        agency="NASA",
        horizon=5,
        channel="federal_contract",
        confidence_filter="all",
        cutoff=date(2024, 12, 31),
    )
    assert summary["firms_with_signal"] == 1
    assert summary["observed_dollars"] == 500_000.0
    assert summary["dollars_per_phase_ii_dollar"] == 0.5
    assert firms.iloc[0]["first_event_date"] == date(2017, 1, 1)


def test_wilson_interval_contains_observed_rate():
    low, high = MODULE.wilson_interval(20, 100)
    assert low < 0.2 < high


def test_deobligation_only_contract_is_not_a_commercialization_signal():
    eligible = pd.DataFrame(
        [{"firm_id": "uei:A", "anchor_date": date(2015, 1, 1), "phase_ii_dollars": 1_000_000}]
    )
    events = pd.DataFrame(
        [{"firm_id": "uei:A", "event_date": date(2017, 1, 1), "amount": -25_000.0}]
    )
    summary, _ = MODULE.summarize_channel(
        eligible,
        events,
        agency="NASA",
        horizon=5,
        channel="federal_contract",
        confidence_filter="all",
        cutoff=date(2024, 12, 31),
    )
    assert summary["firms_with_signal"] == 0
    assert summary["observed_dollars"] == 0.0
