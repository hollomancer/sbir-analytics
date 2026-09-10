import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd


SCRIPT = (
    Path(__file__).resolve().parents[3] / "scripts/data/three_agency_commercialization_outcomes.py"
)
SPEC = importlib.util.spec_from_file_location("three_agency_commercialization_outcomes", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_agency_scope_is_exact():
    assert (
        MODULE.agency_label(pd.Series({"Agency": "National Aeronautics and Space Administration"}))
        == "NASA"
    )
    assert (
        MODULE.agency_label(pd.Series({"Agency": "Department of Energy", "Branch": "ARPA-E"}))
        == "DOE"
    )
    assert (
        MODULE.agency_label(pd.Series({"Agency": "Department of Defense", "Branch": "Air Force"}))
        == "Air Force"
    )
    assert (
        MODULE.agency_label(
            pd.Series({"Agency": "Department of Defense", "Branch": "Space Development Agency"})
        )
        is None
    )


def test_phase_i_ii_research_exclusion_retains_phase_iii():
    assert MODULE.is_phase_i_ii_research("SR1")
    assert MODULE.is_phase_i_ii_research(
        "SMALL BUSINESS INNOVATION RESEARCH PROGRAM PHASE II ACTION"
    )
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


def test_phase_i_ii_exclusion_normalizes_piid_and_keeps_phase_iii(tmp_path):
    path = tmp_path / "contracts.parquet"
    pd.DataFrame(
        [
            {
                "action_date": "2016-06-01",
                "piid": "FA865019C1234",
                "research": "SR2",
                "vendor_uei": "ABC123DEF456",
                "vendor_name": "Acme",
                "federal_action_obligation": 1_000,
                "transaction_unique_id": "t-sr2",
            },
            {
                "action_date": "2016-07-01",
                "piid": "FA865019C1234",
                "research": "SR3",
                "vendor_uei": "ABC123DEF456",
                "vendor_name": "Acme",
                "federal_action_obligation": 5_000,
                "transaction_unique_id": "t-sr3",
            },
            {
                "action_date": "2016-08-01",
                "piid": "FA865019C1234",
                "research": None,
                "vendor_uei": "ABC123DEF456",
                "vendor_name": "Acme",
                "federal_action_obligation": 2_000,
                "transaction_unique_id": "t-uncoded",
            },
        ]
    ).to_parquet(path)
    dashed = "FA8650-19-C-1234"
    assert MODULE.normalize_piid(dashed) == MODULE.normalize_piid("FA865019C1234")
    cohort = MODULE.CohortData(
        firms=pd.DataFrame(),
        phase_ii_awards=pd.DataFrame(),
        alias_to_firm={"uei:ABC123DEF456": "firm-1"},
        phase_i_ii_contract_ids=frozenset({MODULE.normalize_piid(dashed)}),
        raw_company_names=frozenset(),
    )
    events, stats = MODULE.load_contract_events([path], cohort, date(2024, 12, 31))
    known_ids = cohort.phase_i_ii_contract_ids
    piid = MODULE.normalize_piid(dashed)
    assert stats["phase_i_ii_excluded"] == 2
    assert list(events["event_key"]) == ["t-sr3"]
    assert events.iloc[0]["amount"] == 5_000
    assert MODULE.is_excluded_phase_i_ii_action("SR2", piid, known_ids)
    assert not MODULE.is_excluded_phase_i_ii_action("SR3", piid, known_ids)


def test_same_agency_dollars_floor_per_firm_and_share_at_most_one():
    eligible = pd.DataFrame(
        [
            {"firm_id": "pos", "anchor_date": date(2015, 1, 1), "phase_ii_dollars": 1_000},
            {"firm_id": "deob", "anchor_date": date(2015, 1, 1), "phase_ii_dollars": 1_000},
        ]
    )
    events = pd.DataFrame(
        [
            {
                "firm_id": "pos",
                "event_date": date(2016, 1, 1),
                "amount": 100.0,
                "awarding_agency": "National Aeronautics and Space Administration",
            },
            {
                "firm_id": "pos",
                "event_date": date(2016, 2, 1),
                "amount": -90.0,
                "awarding_agency": "Department of Defense",
            },
            {
                "firm_id": "deob",
                "event_date": date(2016, 1, 1),
                "amount": -25.0,
                "awarding_agency": "National Aeronautics and Space Administration",
            },
        ]
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
    assert summary["observed_dollars"] == 10.0
    assert summary["same_agency_observed_dollars"] == 10.0
    assert summary["same_agency_dollar_share"] == 1.0
    assert summary["same_agency_dollar_share"] <= 1.0


def test_form_d_dedupes_shared_accession_after_identity_collapse(tmp_path):
    path = tmp_path / "form_d.jsonl"
    offering = {
        "accession_number": "0001234567-16-000001",
        "date_of_first_sale": "2016-06-01",
        "filing_date": "2016-06-02",
        "total_amount_sold": 100_000,
        "industry_group": "Computers",
        "cik": "123",
        "securities_types": ["equity"],
    }
    records = [
        {
            "company_name": "Acme, Inc.",
            "match_confidence": {"tier": "high"},
            "offerings": [offering],
        },
        {
            "company_name": "ACME INC",
            "match_confidence": {"tier": "high"},
            "offerings": [offering],
        },
    ]
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    alias_to_firm = {
        f"name:{MODULE.normalized_name('Acme, Inc.')}": "firm-1",
        f"name:{MODULE.normalized_name('ACME INC')}": "firm-1",
    }
    cohort = MODULE.CohortData(
        firms=pd.DataFrame(),
        phase_ii_awards=pd.DataFrame(),
        alias_to_firm=alias_to_firm,
        phase_i_ii_contract_ids=frozenset(),
        raw_company_names=frozenset(),
    )
    events, _ = MODULE.load_form_d_events(path, cohort, date(2024, 12, 31))
    assert len(events) == 1
    assert events.iloc[0]["amount"] == 100_000
    assert events.iloc[0]["firm_id"] == "firm-1"


def test_match_firm_uses_identity_primitives_for_uei_and_duns():
    alias_to_firm = {
        "uei:ABC123DEF456": "firm-uei",
        "duns:123456789": "firm-duns",
    }
    firm, basis = MODULE.match_firm(uei="abc-123-def-456", alias_to_firm=alias_to_firm)
    assert (firm, basis) == ("firm-uei", "uei")
    firm, basis = MODULE.match_firm(duns="123456789.0", alias_to_firm=alias_to_firm)
    assert (firm, basis) == ("firm-duns", "duns")
    firm, basis = MODULE.match_firm(duns="12-345-6789", alias_to_firm=alias_to_firm)
    assert (firm, basis) == ("firm-duns", "duns")
