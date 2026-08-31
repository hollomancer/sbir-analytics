"""Focused invariants for the exploratory Navy transition readout."""

from __future__ import annotations

import json
from datetime import date

import pandas as pd
import pytest

from scripts.data.build_navy_transition_readout import (
    _fiscal_year,
    build_external_signal_panel,
    build_latency_panel,
    build_mechanism_panel,
    description_summary,
    latest_award_grain,
    load_coded_inputs,
    prepare_coded_transactions,
    prepare_navy_sbir,
)


def test_coded_input_matrix_requires_exact_structured_queries(tmp_path) -> None:
    pairs = []
    for code in ("SR3", "ST3"):
        for role, role_term in (
            ("awarding", 'CONTRACTING_AGENCY_ID:"1700"'),
            ("funding", 'FUNDING_AGENCY_ID:"1700"'),
        ):
            parquet = tmp_path / f"{code}-{role}.parquet"
            manifest = tmp_path / f"{code}-{role}.json"
            pd.DataFrame({"_research_code": [code], "research": [code]}).to_parquet(
                parquet, index=False
            )
            terms = [
                "SIGNED_DATE:[1980/10/01,2025/09/30]",
                'CONTRACT_TYPE:"AWARD"',
                role_term,
            ]
            manifest.write_text(
                json.dumps(
                    {
                        "retrieval_complete": True,
                        "row_count": 1,
                        "query": " ".join((f"RESEARCH:{code}", *terms)),
                        "parameters": {"research_code": code, "query_terms": terms},
                    }
                )
            )
            pairs.append((parquet, manifest))

    frame, _provenance = load_coded_inputs(pairs, date(2025, 9, 30))
    assert len(frame) == 4

    invalid = json.loads(pairs[0][1].read_text())
    invalid["parameters"]["query_terms"].append("DEPARTMENT_ID:9700")
    invalid["query"] += " DEPARTMENT_ID:9700"
    pairs[0][1].write_text(json.dumps(invalid))
    with pytest.raises(ValueError, match="unexpected query terms"):
        load_coded_inputs(pairs, date(2025, 9, 30))


def test_federal_fiscal_year_boundary_and_navy_sbir_scope() -> None:
    awards = pd.DataFrame(
        [
            {
                "phase": "Phase I",
                "agency": "Department of Defense",
                "branch": "Navy",
                "award_date": "2024-09-30",
            },
            {
                "phase": "Phase II",
                "agency": "Department of Defense",
                "branch": "Navy",
                "award_date": "2024-10-01",
            },
            {
                "phase": "Phase I",
                "agency": "Department of Defense",
                "branch": "Army",
                "award_date": "2024-10-01",
            },
            {
                "phase": "Phase II",
                "agency": "NASA",
                "branch": "Navy",
                "award_date": "2024-10-01",
            },
            {
                "phase": "Phase III",
                "agency": "Department of Defense",
                "branch": "Navy",
                "award_date": "2024-10-01",
            },
        ]
    )

    fiscal_years = _fiscal_year(pd.Series(["2024-09-30", "2024-10-01"]))
    assert fiscal_years.tolist() == [2024, 2025]

    scoped = prepare_navy_sbir(awards, start_fy=2024, end_fy=2025)
    assert scoped[["analysis_phase", "fiscal_year"]].to_dict("records") == [
        {"analysis_phase": "I", "fiscal_year": 2024},
        {"analysis_phase": "II", "fiscal_year": 2025},
    ]


def test_coded_transactions_union_postfilter_deduplication_and_award_grain() -> None:
    def action(
        piid: str,
        modification: str,
        signed: str,
        research: str,
        awarding: str,
        funding: str,
        description: str,
        transaction_number: str = "1",
    ) -> dict[str, str]:
        return {
            "PIID": piid,
            "modNumber": modification,
            "transactionNumber": transaction_number,
            "signedDate": signed,
            "_research_code": research,
            "agencyID": "9700",
            "contractingOfficeAgencyID": awarding,
            "fundingRequestingAgencyID": funding,
            "referenced_idv_piid": "",
            "referenced_idv_agency_id": "",
            "descriptionOfContractRequirement": description,
            "principalNAICSCode": "541715",
            "productOrServiceCode": "AC13",
            "UEI": f"UEI-{piid}",
            "vendorName": f"Vendor {piid}",
        }

    raw = pd.DataFrame(
        [
            action("A-1", "0", "2024-01-01", "SR3", "1700", "9700", "base"),
            action("A-1", "0", "2024-01-01", "SR3", "1700", "9700", "base"),
            action("A-1", "1", "2024-02-01", "SR3", "1700", "9700", "latest"),
            action(
                "A-1",
                "1",
                "2024-02-01",
                "SR3",
                "9999",
                "1700",
                "latest second transaction",
                "2",
            ),
            # Natural modification order must choose P00003 over P0002 on a
            # signed-date tie; lexical order would select the wrong action.
            action("A-1", "P0002", "2024-02-01", "SR3", "1700", "9700", "x" * 157),
            action("A-1", "P00003", "2024-02-01", "SR3", "1700", "9700", "latest natural"),
            action("B-1", "0", "2024-03-01", "ST3", "9999", "1700", "funded"),
            # Same canonical award/action surfaced with a different contracting
            # sub-tier; top-tier agencyID keeps it at one transaction grain.
            action("B-1", "0", "2024-03-01", "ST3", "2100", "1700", "funded"),
            action("C-1", "0", "2024-04-01", "SR3", "9999", "9999", "not Navy"),
            action("D-1", "0", "2024-05-01", "RD1", "1700", "1700", "not coded"),
            action("E-1", "0", "2025-10-01", "SR3", "1700", "1700", "after cut"),
        ]
    )

    transactions = prepare_coded_transactions(raw, data_cut=date(2025, 9, 30))
    assert len(transactions) == 6
    assert set(transactions["award_key"].str.extract(r"CONT_AWD_([^_]+)")[0]) == {
        "A-1",
        "B-1",
    }
    assert transactions["don_awarding"].any()
    assert transactions["don_funding"].any()
    assert transactions["award_key"].str.contains("_9700_").all()
    funding_only = transactions.loc[transactions["award_key"].str.contains("B-1")].iloc[0]
    assert not funding_only["don_awarding"]
    assert funding_only["don_funding"]

    awards = latest_award_grain(transactions)
    assert len(awards) == 2
    assert (
        awards.loc[awards["award_key"].str.contains("A-1"), "description"].item()
        == "latest natural"
    )
    a_award = awards.loc[awards["award_key"].str.contains("A-1")].iloc[0]
    assert a_award["don_awarding"]
    assert a_award["don_funding"]
    assert "upper-bound" in description_summary(awards)["bound"]


def test_mechanism_panel_blocks_constant_input_and_estimates_zero_phi() -> None:
    blocked = pd.DataFrame(
        {
            "description": ["", ""],
            "naics_code": ["541715", ""],
            "psc_code": ["AC13", "AC13"],
        }
    )
    blocked_result = build_mechanism_panel(blocked)
    assert blocked_result["status"] == "blocked_constant_input"
    assert blocked_result["phi"] is None

    independent = pd.DataFrame(
        {
            "description": ["text", "text", "", ""],
            "naics_code": ["541715", "", "541715", ""],
            "psc_code": ["AC13"] * 4,
        }
    )
    estimated = build_mechanism_panel(independent)
    assert estimated["status"] == "estimated"
    assert estimated["phi"] == 0.0
    assert estimated["near_zero"] is True


def test_latency_excludes_pre_award_history_and_right_censors_unmatched_award() -> None:
    navy_sbir = pd.DataFrame(
        [
            {
                "phase": "Phase II",
                "analysis_phase": "II",
                "award_id": "II-1",
                "company_uei": "ABCDEFGHIJKL",
                "company_duns": "",
                "company_name": "Alpha Labs",
                "agency": "Department of Defense",
                "branch": "Navy",
                "award_date": "2022-01-01",
                "contract_end_date": "2023-01-01",
            },
            {
                "phase": "Phase II",
                "analysis_phase": "II",
                "award_id": "II-2",
                "company_uei": "MNOPQRSTUVWX",
                "company_duns": "",
                "company_name": "Beta Corp",
                "agency": "Department of Defense",
                "branch": "Navy",
                "award_date": "2022-01-01",
                "contract_end_date": "2023-01-01",
            },
        ]
    )
    transactions = pd.DataFrame(
        {
            "award_key": ["P3-EXISTING", "P3-EXISTING", "P3-DURING", "P3-AFTER"],
            "recipient_uei": ["ABCDEFGHIJKL"] * 4,
            "recipient_name": ["Alpha Labs"] * 4,
            "don_awarding": [True] * 4,
            "action_date": pd.to_datetime(["2021-01-01", "2022-02-01", "2022-06-01", "2024-01-01"]),
            "mod_number": ["0", "1", "0", "0"],
            "_transaction_number_sort": [1, 2, 1, 1],
            "research_code": ["SR3"] * 4,
        }
    )

    summary, survival = build_latency_panel(navy_sbir, transactions, date(2025, 9, 30))
    by_award = survival.set_index("phase_ii_award_id")

    assert summary["event_award_n"] == 1
    assert summary["censored_award_n"] == 1
    assert summary["negative_latency_n"] == 1
    assert "lower bound" in summary["bound"]
    assert "not an identified bound" in summary["bound"]
    assert by_award.loc["II-1", "event_date"] == date(2022, 6, 1)
    assert bool(by_award.loc["II-1", "event_observed"])
    assert not bool(by_award.loc["II-2", "event_observed"])


def test_external_signal_panel_filters_dates_deduplicates_tiers_and_emits_no_names() -> None:
    navy_sbir = pd.DataFrame(
        {"company_name": ["Alpha Labs", "Alpha Labs", "Beta Corp", "Gamma Systems"]}
    )
    form_d_records = [
        {
            "company_name": "Alpha Labs",
            "match_confidence": {"tier": "medium"},
            "offerings": [
                {
                    "filing_date": "2024-09-01",
                    "total_amount_sold": 1,
                    "is_business_combination": False,
                }
            ],
        },
        {
            "company_name": "Alpha Labs",
            "match_confidence": {"tier": "high"},
            "offerings": [
                {
                    "filing_date": "2026-08-31",
                    "total_amount_sold": 2,
                    "is_business_combination": False,
                }
            ],
        },
        {
            "company_name": "Beta Corp",
            "match_confidence": {"tier": "medium"},
            "offerings": [
                {
                    "filing_date": "2026-01-01",
                    "total_amount_sold": 3,
                    "is_business_combination": False,
                }
            ],
        },
        {
            "company_name": "Gamma Systems",
            "match_confidence": {"tier": "high"},
            "offerings": [
                {
                    "filing_date": "2024-08-31",
                    "total_amount_sold": 4,
                    "is_business_combination": False,
                },
                {
                    "filing_date": "2026-01-01",
                    "total_amount_sold": 5,
                    "is_business_combination": True,
                },
            ],
        },
        {
            "company_name": "Outside Firm",
            "match_confidence": {"tier": "high"},
            "offerings": [
                {
                    "filing_date": "2026-01-01",
                    "total_amount_sold": 6,
                    "is_business_combination": False,
                }
            ],
        },
    ]
    ma_records = [
        {
            "company_name": "Alpha Labs",
            "efts_detail": {
                "efts_tier": "medium",
                "latest_mention_date": "2026-01-01",
                "mention_types": ["acquisition"],
            },
        },
        {
            "company_name": "Beta Corp",
            "efts_detail": {
                "efts_tier": "high",
                "latest_mention_date": "2026-08-31",
                "mention_types": ["ma_definitive"],
            },
        },
        {
            "company_name": "Gamma Systems",
            "efts_detail": {
                "efts_tier": "medium",
                "latest_mention_date": "2024-09-01",
                "mention_types": ["subsidiary"],
            },
        },
        {
            "company_name": "Outside Firm",
            "efts_detail": {
                "efts_tier": "high",
                "latest_mention_date": "2026-01-01",
                "mention_types": ["acquisition"],
            },
        },
    ]

    result = build_external_signal_panel(
        navy_sbir, form_d_records, ma_records, as_of=date(2026, 8, 31)
    )

    assert result["window_start"] == "2024-09-01"
    assert result["navy_firm_n"] == 3
    assert result["form_d_positive_raise_firms"] == {"high": 1, "medium": 1, "total": 2}
    assert result["efts_acquisition_firms"] == {
        "status": "blocked_missing_type_specific_dates",
        "high": None,
        "medium": None,
        "total": None,
    }
    assert result["either_recent_signal_firms"] == {
        "status": "blocked_by_efts_branch",
        "high": None,
        "medium": None,
        "total": None,
    }

    aggregate_output = json.dumps(result).casefold()
    for name in ("alpha", "beta", "gamma", "outside"):
        assert name not in aggregate_output
