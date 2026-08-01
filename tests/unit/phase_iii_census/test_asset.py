from pathlib import Path

import pandas as pd
import pytest
from dagster import Output, build_asset_context

from sbir_analytics.assets.phase_iii_census import assets as census_assets
from sbir_analytics.assets.phase_iii_census.criteria import CensusInputError


pytestmark = pytest.mark.fast


def _prior_source() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "award_id": "PRIOR-1",
                "recipient_uei": "UEI-1",
                "agency": "DEPARTMENT A",
                "sub_agency": "COMPONENT A",
                "office": "OFFICE A",
                "naics_code": "541715",
                "psc_code": "AC13",
                "title": "Prior work",
                "abstract": "Prior abstract",
                "period_of_performance_end": "2020-12-31",
                "cet": None,
            }
        ]
    )


def _contract_source() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "contract_id": "PIID-1",
                "vendor_uei": "UEI-1",
                "awarding_agency_name": "DEPARTMENT A",
                "awarding_sub_tier_agency_name": "COMPONENT A",
                "awarding_office_name": "OFFICE A",
                "naics_code": "541715",
                "psc_code": "AC13",
                "transaction_description": "Follow-on work",
                "action_date": "2021-01-01",
                "extent_competed": "FULL AND OPEN COMPETITION",
                "federal_action_obligation": -25,
                "research": None,
                "sbir_phase": None,
                "transaction_unique_id": "TRANSACTION-1",
                "generated_unique_award_id": "GENERATED-AWARD-1",
            }
        ]
    )


def test_data_cut_parser_requires_explicit_canonical_iso_date(monkeypatch) -> None:
    monkeypatch.delenv(census_assets.DATA_CUT_ENV, raising=False)

    with pytest.raises(CensusInputError, match="Set .*DATA_CUT_DATE"):
        census_assets.parse_census_data_cut_date()

    assert census_assets.parse_census_data_cut_date("2025-12-31").isoformat() == "2025-12-31"
    for invalid in ("", "20251231", "2025-W01-1", "2025-12-31T00:00:00", "2025-02-29"):
        with pytest.raises(CensusInputError, match="ISO YYYY-MM-DD"):
            census_assets.parse_census_data_cut_date(invalid)


def test_asset_writes_exactly_two_parquet_tables_without_headline_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    dropoff_path = tmp_path / "phase_iii_census_dropoff.parquet"
    sensitivity_path = tmp_path / "phase_iii_census_sensitivity.parquet"
    contracts = _contract_source()
    monkeypatch.setattr(census_assets, "DROP_OFF_OUTPUT_PATH", dropoff_path)
    monkeypatch.setattr(census_assets, "SENSITIVITY_OUTPUT_PATH", sensitivity_path)
    monkeypatch.setattr(
        census_assets,
        "_load_contracts",
        lambda: (contracts, Path("synthetic/contracts.parquet")),
    )
    monkeypatch.setenv(census_assets.DATA_CUT_ENV, "2025-12-31")

    result = census_assets.phase_iii_census(build_asset_context(), _prior_source())

    assert isinstance(result, Output)
    assert sorted(path.name for path in tmp_path.glob("*.parquet")) == [
        "phase_iii_census_dropoff.parquet",
        "phase_iii_census_sensitivity.parquet",
    ]
    persisted_dropoff = pd.read_parquet(dropoff_path)
    persisted_sensitivity = pd.read_parquet(sensitivity_path)
    pd.testing.assert_frame_equal(persisted_dropoff, result.value["dropoff"])
    pd.testing.assert_frame_equal(persisted_sensitivity, result.value["sensitivity"])
    assert len(persisted_dropoff) == 6
    assert len(persisted_sensitivity) == 6

    metadata_keys = set(result.metadata)
    assert metadata_keys == {
        "dropoff_path",
        "sensitivity_path",
        "contracts_path",
        "census_data_cut_date",
        "frozen_spec_commit",
        "ordered_clauses",
        "reproducibility",
    }
    assert not any(
        token in key.lower()
        for key in metadata_keys
        for token in ("headline", "selected_cell", "preferred_cell")
    )
