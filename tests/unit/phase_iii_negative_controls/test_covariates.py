"""Tests for arm-blind Phase III control-matching covariates."""

import pandas as pd
import pytest

from sbir_analytics.assets.phase_iii_negative_controls import (
    CovariateInputError,
    build_firm_covariates,
    build_treated_firm_frame,
    summarize_covariate_coverage,
)


def _firms(*ueis: str) -> pd.DataFrame:
    return pd.DataFrame({"firm_id": ueis, "firm_ueis": [(uei,) for uei in ueis]})


def _sam(*rows: tuple[str, str, str]) -> pd.DataFrame:
    return pd.DataFrame(
        rows,
        columns=("unique_entity_id", "primary_naics", "physical_address_state"),
    )


def _contract(
    uei: str,
    action_date: str,
    *,
    psc: str = "A123",
    categories: str | None = "{small_business,woman_owned}",
) -> dict[str, object]:
    return {
        "vendor_uei": uei,
        "action_date": action_date,
        "product_or_service_code": psc,
        "metadata": {"business_categories": categories},
    }


def test_covariates_use_only_unanimous_earliest_contract_rows() -> None:
    firms = _firms("TREATEDUEI01")
    sam = _sam(("TREATEDUEI01", "541715", "va"))
    contracts = pd.DataFrame(
        [
            _contract("TREATEDUEI01", "2012-04-05"),
            _contract(
                "TREATEDUEI01",
                "2020-01-01",
                psc="R425",
                categories="{manufacturer_of_goods}",
            ),
        ]
    )

    result = build_firm_covariates(firms, sam, contracts)

    assert result.iloc[0].to_dict() == {
        "firm_id": "TREATEDUEI01",
        "firm_ueis": ("TREATEDUEI01",),
        "primary_naics": "541715",
        "first_contract_business_size": "small_business",
        "state": "VA",
        "first_contract_year": 2012,
        "psc_family": "A",
        "first_contract_date": pd.Timestamp("2012-04-05").date(),
        "first_contract_rows": 1,
        "match_eligible": True,
        "covariate_exclusion_reasons": (),
    }


def test_absent_small_business_token_means_other_than_small_when_array_is_present() -> None:
    result = build_firm_covariates(
        _firms("CONTROLUEI01"),
        _sam(("CONTROLUEI01", "334511", "MD")),
        pd.DataFrame([_contract("CONTROLUEI01", "2010-01-01", categories="{woman_owned}")]),
    )

    assert result.iloc[0].first_contract_business_size == "other_than_small_business"
    assert bool(result.iloc[0].match_eligible) is True


@pytest.mark.parametrize("categories", [None, "small_business", "{small business}"])
def test_missing_or_unparseable_business_categories_are_not_imputed(categories) -> None:
    result = build_firm_covariates(
        _firms("CONTROLUEI02"),
        _sam(("CONTROLUEI02", "334511", "MD")),
        pd.DataFrame([_contract("CONTROLUEI02", "2010-01-01", categories=categories)]),
    )

    assert result.iloc[0].first_contract_business_size is None
    assert "first_contract_business_size_missing" in result.iloc[0].covariate_exclusion_reasons
    assert bool(result.iloc[0].match_eligible) is False


def test_conflicting_earliest_day_size_and_psc_are_explicit() -> None:
    result = build_firm_covariates(
        _firms("CONTROLUEI03"),
        _sam(("CONTROLUEI03", "334511", "MD")),
        pd.DataFrame(
            [
                _contract("CONTROLUEI03", "2010-01-01", psc="A123"),
                _contract(
                    "CONTROLUEI03",
                    "2010-01-01",
                    psc="R425",
                    categories="{manufacturer_of_goods}",
                ),
            ]
        ),
    )

    assert result.iloc[0].first_contract_business_size is None
    assert result.iloc[0].psc_family is None
    assert set(result.iloc[0].covariate_exclusion_reasons) == {
        "first_contract_business_size_conflict",
        "psc_family_conflict",
    }


def test_same_builder_handles_multi_uei_identity_envelope_without_arm_flag() -> None:
    firms = pd.DataFrame(
        {"firm_id": ["ENVELOPE-1"], "firm_ueis": [("CONTROLUEI04", "CONTROLUEI05")]}
    )
    sam = _sam(
        ("CONTROLUEI04", "541715", "CA"),
        ("CONTROLUEI05", "541715", "CA"),
    )
    contracts = pd.DataFrame([_contract("CONTROLUEI05", "2011-02-03")])

    result = build_firm_covariates(firms, sam, contracts)

    assert bool(result.iloc[0].match_eligible) is True
    assert result.iloc[0].first_contract_year == 2011


def test_one_uei_cannot_belong_to_two_firm_envelopes() -> None:
    firms = pd.DataFrame(
        {"firm_id": ["ONE", "TWO"], "firm_ueis": [("CONTROLUEI06",), ("CONTROLUEI06",)]}
    )

    with pytest.raises(CovariateInputError, match="multiple firm envelopes"):
        build_firm_covariates(firms, _sam(("CONTROLUEI06", "541715", "CA")), pd.DataFrame())


def test_treated_frame_is_exact_uei_only() -> None:
    phase_ii = pd.DataFrame(
        {"recipient_uei": [" treateduei07 ", None, "bad", "TREATEDUEI07", "TREATEDUEI08"]}
    )

    result = build_treated_firm_frame(phase_ii)

    assert result.to_dict(orient="records") == [
        {"firm_id": "TREATEDUEI07", "firm_ueis": ("TREATEDUEI07",)},
        {"firm_id": "TREATEDUEI08", "firm_ueis": ("TREATEDUEI08",)},
    ]


def test_coverage_reports_counts_without_an_acceptance_threshold() -> None:
    covariates = build_firm_covariates(
        _firms("CONTROLUEI09", "CONTROLUEI10"),
        _sam(("CONTROLUEI09", "541715", "CA")),
        pd.DataFrame([_contract("CONTROLUEI09", "2011-02-03")]),
    )

    result = summarize_covariate_coverage(covariates, arm="control")

    first_year = result.loc[result["covariate"].eq("first_contract_year")].iloc[0]
    assert first_year.to_dict() == {
        "arm": "control",
        "covariate": "first_contract_year",
        "observed_firms": 1,
        "missing_firms": 1,
        "conflict_firms": 0,
        "total_firms": 2,
    }
