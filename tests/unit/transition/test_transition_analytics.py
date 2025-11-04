import pandas as pd

from src.transition.analysis.analytics import TransitionAnalytics


def test_award_transition_rate_basic():
    # Awards: 3 awards total
    awards = pd.DataFrame(
        [
            {"award_id": "A1", "Company": "Acme Inc"},
            {"award_id": "A2", "Company": "Beta LLC"},
            {"award_id": "A3", "Company": "Gamma Corp"},
        ]
    )

    # Transitions: A1 and A2 above threshold (>= 0.60)
    transitions = pd.DataFrame(
        [
            {"award_id": "A1", "score": 0.80},
            {"award_id": "A2", "score": 0.70},
            {"award_id": "A3", "score": 0.10},  # below threshold
        ]
    )

    analytics = TransitionAnalytics(score_threshold=0.60)
    rate = analytics.compute_award_transition_rate(awards, transitions)

    assert rate.numerator == 2
    assert rate.denominator == 3
    assert abs(rate.rate - (2 / 3)) < 1e-9


def test_company_transition_rate_with_mixed_ids():
    # Four awards across three companies:
    # - Company1 identified by UEI (two awards)
    # - Company2 identified by DUNS (one award)
    # - Company3 identified by name only (one award)
    awards = pd.DataFrame(
        [
            {"award_id": "A1", "Company": "Acme Inc", "UEI": "U1", "Duns": None},
            {"award_id": "A2", "Company": "Acme Incorporated", "UEI": "U1", "Duns": None},
            {"award_id": "A3", "Company": "Beta LLC", "UEI": None, "Duns": "D1"},
            {"award_id": "A4", "Company": "Gamma Corp", "UEI": None, "Duns": None},
        ]
    )
    transitions = pd.DataFrame(
        [
            {"award_id": "A1", "score": 0.90},  # Company U1 transitioned
            {"award_id": "A4", "score": 0.70},  # Company name:gamma corp transitioned
            {"award_id": "A3", "score": 0.10},  # below threshold
        ]
    )

    analytics = TransitionAnalytics(score_threshold=0.60)
    rate, per_company = analytics.compute_company_transition_rate(awards, transitions)

    # There should be 3 unique companies (uei:U1, duns:D1, name:gamma corp)
    assert rate.denominator == 3
    assert rate.numerator == 2
    assert abs(rate.rate - (2 / 3)) < 1e-9

    # Validate per-company breakdown
    # Normalize for easy lookup
    per_company_idx = per_company.set_index("company_id")

    # uei:U1 -> 2 total awards, 1 transitioned
    assert per_company_idx.loc["uei:U1", "total_awards"] == 2
    assert per_company_idx.loc["uei:U1", "transitioned_awards"] == 1
    assert bool(per_company_idx.loc["uei:U1", "transitioned"]) is True

    # duns:D1 -> 1 total award, 0 transitioned
    assert per_company_idx.loc["duns:D1", "total_awards"] == 1
    assert per_company_idx.loc["duns:D1", "transitioned_awards"] == 0
    assert bool(per_company_idx.loc["duns:D1", "transitioned"]) is False

    # name:gamma corp -> 1 total award, 1 transitioned
    assert per_company_idx.loc["name:gamma corp", "total_awards"] == 1
    assert per_company_idx.loc["name:gamma corp", "transitioned_awards"] == 1
    assert bool(per_company_idx.loc["name:gamma corp", "transitioned"]) is True


def test_phase_effectiveness_rates():
    # Phases normalized from various inputs ("Phase I", "I", etc.)
    awards = pd.DataFrame(
        [
            {"award_id": "A1", "Phase": "I"},
            {"award_id": "A2", "Phase": "Phase I"},
            {"award_id": "A3", "Phase": "II"},
            {"award_id": "A4", "Phase": "Phase II"},
        ]
    )
    transitions = pd.DataFrame(
        [
            {"award_id": "A2", "score": 0.75},  # Phase I transitioned
            {"award_id": "A4", "score": 0.90},  # Phase II transitioned
        ]
    )

    analytics = TransitionAnalytics(score_threshold=0.60)
    phase_df = analytics.compute_phase_effectiveness(awards, transitions)

    # Expected: Phase I -> 2 total, 1 transitioned (rate 0.5)
    #           Phase II -> 2 total, 1 transitioned (rate 0.5)
    rec_i = phase_df.loc[phase_df["phase"] == "I"].iloc[0].to_dict()
    rec_ii = phase_df.loc[phase_df["phase"] == "II"].iloc[0].to_dict()

    assert rec_i["total_awards"] == 2
    assert rec_i["transitioned_awards"] == 1
    assert abs(rec_i["rate"] - 0.5) < 1e-9

    assert rec_ii["total_awards"] == 2
    assert rec_ii["transitioned_awards"] == 1
    assert abs(rec_ii["rate"] - 0.5) < 1e-9


def test_by_agency_rates():
    awards = pd.DataFrame(
        [
            {"award_id": "A1", "awarding_agency_name": "NASA"},
            {"award_id": "A2", "awarding_agency_name": "NASA"},
            {"award_id": "A3", "awarding_agency_name": "DEPT OF DEFENSE"},
            {"award_id": "A4", "awarding_agency_name": "DEPT OF DEFENSE"},
        ]
    )

    transitions = pd.DataFrame(
        [
            {"award_id": "A1", "score": 0.80},  # NASA transitioned
            {"award_id": "A2", "score": 0.70},  # NASA transitioned
            {"award_id": "A3", "score": 0.40},  # below threshold
        ]
    )

    analytics = TransitionAnalytics(score_threshold=0.60)
    agency_df = analytics.compute_by_agency(awards, transitions)

    # Normalize for lookup
    idx = agency_df.set_index("agency")

    # NASA: 2 total, 2 transitioned (rate 1.0)
    assert idx.loc["NASA", "total_awards"] == 2
    assert idx.loc["NASA", "transitioned_awards"] == 2
    assert abs(idx.loc["NASA", "rate"] - 1.0) < 1e-9

    # DEPT OF DEFENSE: 2 total, 0 transitioned (rate 0.0)
    assert idx.loc["DEPT OF DEFENSE", "total_awards"] == 2
    assert idx.loc["DEPT OF DEFENSE", "transitioned_awards"] == 0
    assert abs(idx.loc["DEPT OF DEFENSE", "rate"] - 0.0) < 1e-9


def test_avg_time_to_transition_by_agency_happy_path():
    # Choose dates to produce exact day deltas:
    # NASA: A1 -> 30 days, A2 -> 60 days (avg=45.0, p50=45.0, p90=57.0)
    # DOD:  A3 -> 15 days
    awards = pd.DataFrame(
        [
            {"award_id": "A1", "awarding_agency_name": "NASA", "award_date": "2022-01-01"},
            {"award_id": "A2", "awarding_agency_name": "NASA", "award_date": "2022-01-01"},
            {
                "award_id": "A3",
                "awarding_agency_name": "DEPT OF DEFENSE",
                "award_date": "2022-01-01",
            },
        ]
    )
    transitions = pd.DataFrame(
        [
            {"award_id": "A1", "contract_id": "C1", "score": 0.9},
            {"award_id": "A2", "contract_id": "C2", "score": 0.9},
            {"award_id": "A3", "contract_id": "C3", "score": 0.9},
        ]
    )
    contracts = pd.DataFrame(
        [
            {"contract_id": "C1", "action_date": "2022-01-31"},  # 30 days after A1 award_date
            {"contract_id": "C2", "action_date": "2022-03-02"},  # 60 days after A2 award_date
            {"contract_id": "C3", "action_date": "2022-01-16"},  # 15 days after A3 award_date
        ]
    )

    analytics = TransitionAnalytics(score_threshold=0.60)
    ttt_df = analytics.compute_avg_time_to_transition_by_agency(awards, transitions, contracts)

    # Normalize index
    idx = ttt_df.set_index("agency")

    # NASA row assertions
    assert int(idx.loc["NASA", "n"]) == 2
    assert abs(float(idx.loc["NASA", "avg_days"]) - 45.0) < 1e-6
    assert abs(float(idx.loc["NASA", "p50_days"]) - 45.0) < 1e-6
    # pandas linear quantile for q=0.9 between 30 and 60 => 30 + 0.9*(60-30) = 57
    assert abs(float(idx.loc["NASA", "p90_days"]) - 57.0) < 1e-6

    # DOD row sanity
    assert int(idx.loc["DEPT OF DEFENSE", "n"]) == 1
    assert abs(float(idx.loc["DEPT OF DEFENSE", "avg_days"]) - 15.0) < 1e-6
    assert abs(float(idx.loc["DEPT OF DEFENSE", "p50_days"]) - 15.0) < 1e-6
    assert abs(float(idx.loc["DEPT OF DEFENSE", "p90_days"]) - 15.0) < 1e-6


def test_time_to_transition_returns_empty_when_missing_inputs():
    awards = pd.DataFrame([{"award_id": "A1", "Agency": "NASA"}])
    transitions = pd.DataFrame([{"award_id": "A1", "contract_id": "C1", "score": 0.9}])

    analytics = TransitionAnalytics(score_threshold=0.60)

    # Missing contracts_df -> empty result
    out1 = analytics.compute_avg_time_to_transition_by_agency(awards, transitions, None)
    assert out1.empty

    # Missing necessary columns -> empty result
    contracts_bad = pd.DataFrame([{"piid": "C1"}])  # missing action_date/start_date
    out2 = analytics.compute_avg_time_to_transition_by_agency(awards, transitions, contracts_bad)
    assert out2.empty


def test_summarize_compiles_minimal_payloads():
    awards = pd.DataFrame(
        [
            {
                "award_id": "A1",
                "Company": "Acme",
                "UEI": "U1",
                "Phase": "I",
                "awarding_agency_name": "NASA",
            },
            {
                "award_id": "A2",
                "Company": "Beta",
                "UEI": "U2",
                "Phase": "II",
                "awarding_agency_name": "NASA",
            },
        ]
    )
    transitions = pd.DataFrame(
        [
            {"award_id": "A1", "contract_id": "C1", "score": 0.9},
            {"award_id": "A2", "contract_id": "C2", "score": 0.5},  # below threshold
        ]
    )
    contracts = pd.DataFrame(
        [
            {"contract_id": "C1", "action_date": "2022-02-01"},
            {"contract_id": "C2", "action_date": "2022-03-01"},
        ]
    )

    analytics = TransitionAnalytics(score_threshold=0.60)
    summary = analytics.summarize(awards, transitions, contracts)

    # Basic keys present
    assert "score_threshold" in summary
    assert "award_transition_rate" in summary
    assert "company_transition_rate" in summary

    # Optional aggregates exist and are serializable
    assert isinstance(summary.get("top_agencies", []), list)
    assert isinstance(summary.get("phase_effectiveness", []), list)
    assert isinstance(summary.get("avg_time_to_transition_by_agency", []), list)


import pytest


pytestmark = pytest.mark.fast
