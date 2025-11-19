import pandas as pd
import pytest


pytestmark = pytest.mark.fast



def _unwrap_output(result):
    """
    Helper to unwrap Dagster Output or bare values.

    The transition assets return an Output(value=..., metadata=...).
    In case Dagster isn't installed (shim), the object still has 'value'.
    If behavior changes, fall back to returning the object itself.
    """
    if hasattr(result, "value"):
        return result.value, getattr(result, "metadata", None)
    return result, None


def test_signals_and_boosts_for_name_fuzzy(monkeypatch, tmp_path):
    # Run all outputs into a temp working directory
    monkeypatch.chdir(tmp_path)

    # Set deterministic boost parameters
    monkeypatch.setenv("SBIR_ETL__TRANSITION__DATE_WINDOW_YEARS", "5")
    monkeypatch.setenv("SBIR_ETL__TRANSITION__DATE_BOOST_MAX", "0.08")  # <=2y → 0.08
    monkeypatch.setenv("SBIR_ETL__TRANSITION__AGENCY_BOOST", "0.05")
    monkeypatch.setenv("SBIR_ETL__TRANSITION__AMOUNT_BOOST", "0.03")
    monkeypatch.setenv("SBIR_ETL__TRANSITION__ID_LINK_BOOST", "0.10")
    monkeypatch.setenv("SBIR_ETL__TRANSITION__LIMIT_PER_AWARD", "50")

    # Import locally so env/working dir changes apply
    from src.assets.transition import (  # noqa: WPS433
        AssetExecutionContext,
        transformed_transition_scores,
    )

    # Contracts sample: one contract intended to match A2 by fuzzy name; include fields for all boosts
    contracts_df = pd.DataFrame(
        [
            {
                "contract_id": "C2",
                "piid": "PIID-BOOST",
                "fain": None,
                "vendor_uei": None,
                "vendor_duns": None,
                "vendor_name": "Acme Corporation",
                "action_date": "2023-02-01",
                "obligated_amount": 50000,
                "awarding_agency_code": "9700",
                "awarding_agency_name": "DEPT OF DEFENSE",
            },
        ]
    )

    # Enriched SBIR awards minimal surface for A2 with agency/date/amount and PIID match
    awards_df = pd.DataFrame(
        [
            {
                "award_id": "A2",
                "Company": "Acme Corp",
                "UEI": None,
                "Duns": None,
                "Agency": "DEPT OF DEFENSE",  # Agency alignment by name
                "awarding_agency_code": "9700",  # Agency alignment by code
                "award_date": "2022-09-01",  # < 2 years before contract action_date
                "Award Amount": 55000,  # Amount sanity (~similar to contract)
                "PIID": "PIID-BOOST",  # ID link (PIID)
            },
        ]
    )

    # Vendor resolution result pointing to name-based vendor id for A2
    vendor_res_df = pd.DataFrame(
        [
            {
                "contract_id": "C2",
                "matched_vendor_id": "name:acme corp",
                "match_method": "name_fuzzy",
                "confidence": 0.9,
            },
        ]
    )

    ctx = AssetExecutionContext()
    scores_out = transformed_transition_scores(ctx, vendor_res_df, contracts_df, awards_df)
    scores_df, _ = _unwrap_output(scores_out)

    # Expect 1 candidate: A2↔C2 via fuzzy + all boosts
    assert isinstance(scores_df, pd.DataFrame)
    assert {"award_id", "contract_id", "score", "method", "signals", "computed_at"}.issubset(
        set(scores_df.columns)
    )
    assert len(scores_df) == 1

    row = scores_df.iloc[0]
    assert row["award_id"] == "A2"
    assert row["contract_id"] == "C2"
    assert row["method"] == "name_fuzzy"

    # Expected signals: method + the four boost signals
    expected_signals = ["name_fuzzy", "date_overlap", "agency_align", "piid_link", "amount_sanity"]
    assert row["signals"] == expected_signals

    # Base for name_fuzzy = 0.7; boosts: +0.08 (date) +0.05 (agency) +0.10 (PIID) +0.03 (amount) = +0.26
    # Total expected score = 0.96
    expected_score = 0.96
    assert abs(float(row["score"]) - expected_score) < 1e-6
