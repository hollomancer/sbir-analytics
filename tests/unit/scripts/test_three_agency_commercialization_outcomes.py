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


def _award_row(
    company: str,
    *,
    uei: str = "",
    duns: str = "",
    agency: str = "National Aeronautics and Space Administration",
    branch: str = "",
    phase: str = "Phase II",
    contract: str = "NNX-TEST",
) -> dict[str, str]:
    return {
        "Company": company,
        "Agency": agency,
        "Branch": branch,
        "Phase": phase,
        "Program": "SBIR",
        "Contract": contract,
        "Proposal Award Date": "2015-01-15",
        "Award Year": "2015",
        "Award Amount": "100000",
        "UEI": uei,
        "Duns": duns,
    }


def _write_awards(path: Path, rows: list[dict[str, str]]) -> Path:
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


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


def _form_d_record(company_name: str, *, accession: str, cik: str, amount: int = 100_000) -> dict:
    return {
        "company_name": company_name,
        "match_confidence": {"tier": "high"},
        "offerings": [
            {
                "accession_number": accession,
                "date_of_first_sale": "2016-06-01",
                "filing_date": "2016-06-02",
                "total_amount_sold": amount,
                "industry_group": "Computers",
                "cik": cik,
                "securities_types": ["equity"],
            }
        ],
    }


def test_form_d_quarantines_accession_credited_to_multiple_firms(tmp_path):
    path = tmp_path / "form_d.jsonl"
    records = [
        _form_d_record("Acme, Inc.", accession="0001", cik="111"),
        _form_d_record("Other Co", accession="0001", cik="111"),
    ]
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    cohort = MODULE.CohortData(
        firms=pd.DataFrame(),
        phase_ii_awards=pd.DataFrame(),
        alias_to_firm={
            f"name:{MODULE.normalized_name('Acme, Inc.')}": "firm-1",
            f"name:{MODULE.normalized_name('Other Co')}": "firm-2",
        },
        phase_i_ii_contract_ids=frozenset(),
        raw_company_names=frozenset(),
    )
    events, audit = MODULE.load_form_d_events(path, cohort, date(2024, 12, 31))
    assert events.empty
    assert audit["ambiguous_accessions_quarantined"] == 1
    assert audit["ambiguous_event_rows_dropped"] == 2


def test_form_d_quarantines_shared_cik_with_distinct_accessions(tmp_path):
    path = tmp_path / "form_d.jsonl"
    records = [
        _form_d_record("Acme, Inc.", accession="0001", cik="0000123", amount=50_000),
        _form_d_record("Other Co", accession="0002", cik="123", amount=75_000),
        _form_d_record("Solo LLC", accession="0003", cik="999", amount=10_000),
    ]
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    cohort = MODULE.CohortData(
        firms=pd.DataFrame(),
        phase_ii_awards=pd.DataFrame(),
        alias_to_firm={
            f"name:{MODULE.normalized_name('Acme, Inc.')}": "firm-1",
            f"name:{MODULE.normalized_name('Other Co')}": "firm-2",
            f"name:{MODULE.normalized_name('Solo LLC')}": "firm-3",
        },
        phase_i_ii_contract_ids=frozenset(),
        raw_company_names=frozenset(),
    )
    events, audit = MODULE.load_form_d_events(path, cohort, date(2024, 12, 31))
    assert list(events["firm_id"]) == ["firm-3"]
    assert events.iloc[0]["amount"] == 10_000
    assert audit["ambiguous_ciks_quarantined"] == 1
    assert "firm-1" not in set(events["firm_id"])
    assert "firm-2" not in set(events["firm_id"])


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


def test_cohort_keeps_same_name_firms_with_incompatible_uei_and_duns_distinct(tmp_path: Path):
    awards = _write_awards(
        tmp_path / "awards.csv",
        [
            _award_row(
                "Atlas Scientific, LLC",
                uei="ABC123DEF456",
                duns="111111111",
                contract="NNX-ONE",
            ),
            _award_row(
                "ATLAS SCIENTIFIC LLC",
                uei="XYZ789GHJ012",
                duns="222222222",
                contract="NNX-TWO",
            ),
        ],
    )

    cohort = MODULE.build_cohort(awards, date(2024, 12, 31))

    assert set(cohort.firms["firm_id"]) == {"UEI:ABC123DEF456", "UEI:XYZ789GHJ012"}
    assert len(cohort.phase_ii_awards) == 2
    name_alias = f"name:{MODULE.normalized_name('Atlas Scientific LLC')}"
    assert name_alias not in cohort.alias_to_firm
    assert MODULE.match_firm(name="Atlas Scientific LLC", alias_to_firm=cohort.alias_to_firm) == (
        None,
        None,
    )
    assert MODULE.match_firm(
        uei="abc-123-def-456", name="Atlas Scientific LLC", alias_to_firm=cohort.alias_to_firm
    ) == ("UEI:ABC123DEF456", "uei")
    assert MODULE.match_firm(
        duns="222-222-222", name="Atlas Scientific LLC", alias_to_firm=cohort.alias_to_firm
    ) == ("UEI:XYZ789GHJ012", "duns")


def test_noncohort_identifier_conflict_quarantines_cohort_name_alias(tmp_path: Path):
    awards = _write_awards(
        tmp_path / "awards.csv",
        [
            _award_row(
                "Pioneer Systems, Inc.",
                uei="ABC123DEF456",
                duns="111111111",
                contract="NNX-COHORT",
            ),
            _award_row(
                "PIONEER SYSTEMS INC",
                uei="XYZ789GHJ012",
                duns="222222222",
                agency="Department of Health and Human Services",
                phase="Phase I",
                contract="HHS-NONCOHORT",
            ),
        ],
    )

    cohort = MODULE.build_cohort(awards, date(2024, 12, 31))

    assert list(cohort.firms["firm_id"]) == ["UEI:ABC123DEF456"]
    name_alias = f"name:{MODULE.normalized_name('Pioneer Systems Inc')}"
    assert name_alias not in cohort.alias_to_firm
    assert MODULE.match_firm(name="Pioneer Systems Inc", alias_to_firm=cohort.alias_to_firm) == (
        None,
        None,
    )
    assert "uei:XYZ789GHJ012" not in cohort.alias_to_firm


def test_ma_loader_preserves_signal_but_marks_form_d_only_as_non_independent(tmp_path):
    ma_path = tmp_path / "enriched_ma.jsonl"
    ma_path.write_text(
        json.dumps(
            {
                "company_name": "ACME",
                "event_date": "2018-01-01",
                "confidence": "high",
                "acquirer": None,
                "signals": {"form_d_business_combination": True},
                "cross_enrichment": {
                    "relationship_id": "ma_test",
                    "evidence_sources": ["form_d"],
                    "independent_of_form_d": False,
                },
            }
        )
        + "\n"
    )
    cohort = MODULE.CohortData(
        firms=pd.DataFrame(),
        phase_ii_awards=pd.DataFrame(),
        alias_to_firm={"name:ACME": "name:ACME"},
        phase_i_ii_contract_ids=set(),
        raw_company_names=set(),
    )
    events, audit = MODULE.load_ma_events(ma_path, cohort, date(2024, 12, 31))
    assert len(events) == 1
    assert bool(events.iloc[0]["independent_of_form_d"]) is False
    assert events.iloc[0]["relationship_id"] == "ma_test"
    assert audit["form_d_only"] == 1
    assert audit.get("unclassified", 0) == 0


def test_ma_loader_splits_unclassified_from_form_d_only(tmp_path):
    ma_path = tmp_path / "enriched_ma.jsonl"
    ma_path.write_text(
        json.dumps(
            {
                "company_name": "ACME",
                "event_date": "2018-01-01",
                "confidence": "high",
                "acquirer": None,
                "signals": {},
                "cross_enrichment": {
                    "relationship_id": "ma_unclassified",
                    "evidence_sources": [],
                    "independent_of_form_d": False,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    cohort = MODULE.CohortData(
        firms=pd.DataFrame(),
        phase_ii_awards=pd.DataFrame(),
        alias_to_firm={"name:ACME": "name:ACME"},
        phase_i_ii_contract_ids=set(),
        raw_company_names=set(),
    )
    events, audit = MODULE.load_ma_events(ma_path, cohort, date(2024, 12, 31))
    assert len(events) == 1
    assert bool(events.iloc[0]["independent_of_form_d"]) is False
    assert audit.get("form_d_only", 0) == 0
    assert audit["unclassified"] == 1
    assert MODULE.ma_provenance_audit_bucket(["form_d"]) == "form_d_only"
    assert MODULE.ma_provenance_audit_bucket([]) == "unclassified"
    assert MODULE.ma_provenance_audit_bucket(["efts"]) == "independent_of_form_d"


def test_ma_summary_reports_observed_and_independent_signals_separately():
    eligible = pd.DataFrame(
        [{"firm_id": "name:ACME", "anchor_date": date(2015, 1, 1), "phase_ii_dollars": 1}]
    )
    events = pd.DataFrame(
        [
            {
                "firm_id": "name:ACME",
                "event_date": date(2018, 1, 1),
                "amount": 0.0,
                "confidence": "high",
                "independent_of_form_d": False,
            }
        ]
    )
    summary, firms = MODULE.summarize_channel(
        eligible,
        events,
        agency="NASA",
        horizon=5,
        channel="ma",
        confidence_filter="high",
        cutoff=date(2024, 12, 31),
    )
    assert summary["firms_with_signal"] == 1
    assert summary["firms_with_independent_signal"] == 0
    assert bool(firms.iloc[0]["has_signal"]) is True
    assert bool(firms.iloc[0]["independent_signal"]) is False


def test_overlap_does_not_double_count_form_d_derived_ma_as_independent_channel():
    common = {
        "agency": "NASA",
        "horizon_years": 5,
        "confidence_filter": "high",
        "firm_id": "name:ACME",
    }
    firms = pd.DataFrame(
        [
            {
                **common,
                "channel": "federal_contract",
                "has_signal": False,
                "independent_signal": False,
            },
            {**common, "channel": "form_d", "has_signal": True, "independent_signal": True},
            {**common, "channel": "ma", "has_signal": True, "independent_signal": False},
        ]
    )
    overlap = MODULE.build_channel_overlap(firms)
    assert overlap.iloc[0]["pathway"] == "form_d"
    assert overlap.iloc[0]["ma_any_signal_firms"] == 1
    assert overlap.iloc[0]["ma_same_source_only_firms"] == 1


def test_generated_memo_labels_ma_as_candidate_and_form_d_amount_as_not_value(tmp_path):
    rows = []
    for agency in MODULE.AGENCY_LABELS:
        for channel, confidence in (
            ("federal_contract", "all"),
            ("form_d", "high"),
            ("ma", "high"),
        ):
            rows.append(
                {
                    "agency": agency,
                    "horizon_years": MODULE.PRIMARY_HORIZON,
                    "channel": channel,
                    "confidence_filter": confidence,
                    "eligible_firms": 10,
                    "firms_with_independent_signal": 1,
                    "rate": 0.1,
                    "dollars_per_phase_ii_dollar": 0.0,
                }
            )
    output = tmp_path / "memo.md"
    MODULE.write_markdown(pd.DataFrame(rows), pd.DataFrame(), output, date(2024, 12, 31))
    memo = output.read_text()
    assert "M&A candidate rate (high)" in memo
    assert "unvalidated public-record candidates" in memo
    assert "not company, enterprise, or exit value" in memo
    assert MODULE.FORM_D_CHANNEL_AMOUNT_SOLD_MEASURE == "exempt_securities_sold"


def test_write_markdown_guards_zero_eligible_firms(tmp_path):
    rows = []
    for agency in MODULE.AGENCY_LABELS:
        for channel, confidence in (
            ("federal_contract", "all"),
            ("form_d", "high"),
            ("ma", "high"),
        ):
            rows.append(
                {
                    "agency": agency,
                    "horizon_years": MODULE.PRIMARY_HORIZON,
                    "channel": channel,
                    "confidence_filter": confidence,
                    "eligible_firms": 0,
                    "firms_with_independent_signal": 0,
                    "rate": 0.0,
                    "dollars_per_phase_ii_dollar": 0.0,
                }
            )
    output = tmp_path / "memo.md"
    MODULE.write_markdown(pd.DataFrame(rows), pd.DataFrame(), output, date(2024, 12, 31))
    memo = output.read_text()
    assert "n/a" in memo
