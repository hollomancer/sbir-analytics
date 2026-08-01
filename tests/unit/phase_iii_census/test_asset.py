import hashlib
import json
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


def _write_contract_manifest(path: Path) -> None:
    provenance = {
        "canonical_table": "rpt.transaction_search",
        "physical_table": "rpt.transaction_search_fpds",
        "member": "9247.dat.gz",
        "ordered_columns_sha256": "a" * 64,
        "column_count": 300,
        "toc_sha256": "b" * 64,
        "vendor_filter_sha256": "c" * 64,
        "output_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "provenance_version": 1,
    }
    path.with_suffix(".checks.json").write_text(
        json.dumps({"source_provenance": provenance}), encoding="utf-8"
    )


def test_data_cut_parser_requires_explicit_canonical_iso_date(monkeypatch) -> None:
    monkeypatch.delenv(census_assets.DATA_CUT_ENV, raising=False)

    with pytest.raises(CensusInputError, match="Set .*DATA_CUT_DATE"):
        census_assets.parse_census_data_cut_date()

    assert census_assets.parse_census_data_cut_date("2025-12-31").isoformat() == "2025-12-31"
    for invalid in ("", "20251231", "2025-W01-1", "2025-12-31T00:00:00", "2025-02-29"):
        with pytest.raises(CensusInputError, match="ISO YYYY-MM-DD"):
            census_assets.parse_census_data_cut_date(invalid)


def test_contract_loader_requires_matching_source_manifest(tmp_path: Path, monkeypatch) -> None:
    contracts_path = tmp_path / "contracts.parquet"
    _contract_source().to_parquet(contracts_path)
    monkeypatch.setattr(census_assets, "CONTRACTS_PRIMARY_PATH", contracts_path)
    monkeypatch.setattr(census_assets, "CONTRACTS_FALLBACK_PATH", tmp_path / "missing.parquet")

    with pytest.raises(CensusInputError, match="no provenance manifest"):
        census_assets._load_contracts()

    _write_contract_manifest(contracts_path)
    loaded, source_path = census_assets._load_contracts()
    assert source_path == contracts_path
    pd.testing.assert_frame_equal(loaded, _contract_source())

    manifest_path = contracts_path.with_suffix(".checks.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_provenance"]["provenance_version"] = 0
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(CensusInputError, match="unsupported version"):
        census_assets._load_contracts()

    _write_contract_manifest(contracts_path)
    contracts_path.write_bytes(contracts_path.read_bytes() + b"tampered")
    with pytest.raises(CensusInputError, match="checksum"):
        census_assets._load_contracts()


def test_census_prior_provenance_fails_closed_without_dedicated_v2_source(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(census_assets.SBIR_AWARDS_ENV, raising=False)

    with pytest.raises(CensusInputError, match="requires the dedicated v2 SBIR.gov source"):
        census_assets._verify_phase_ii_provenance(
            _prior_source(), Path("missing-contracts.parquet")
        )


def test_census_prior_provenance_rejects_non_object_phase_ii_manifest(
    tmp_path: Path, monkeypatch
) -> None:
    sbir_path = tmp_path / "sbir.parquet"
    phase_ii_path = tmp_path / "phase_ii.parquet"
    sbir_path.write_bytes(b"synthetic")
    phase_ii_path.with_suffix(".checks.json").write_text("[]", encoding="utf-8")
    monkeypatch.setenv(census_assets.SBIR_AWARDS_ENV, str(sbir_path))
    monkeypatch.setenv(census_assets.PHASE_II_OUTPUT_ENV, str(phase_ii_path))
    monkeypatch.setattr(census_assets.pd, "read_parquet", lambda _path: pd.DataFrame())
    monkeypatch.setattr(
        census_assets,
        "verify_sbir_gov_materialization",
        lambda _path, _frame: {"output": {"sha256": "a" * 64}},
    )

    with pytest.raises(CensusInputError, match="must be a JSON object"):
        census_assets._verify_phase_ii_provenance(
            _prior_source(), Path("synthetic-contracts.parquet")
        )


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
    monkeypatch.setattr(
        census_assets,
        "_verify_phase_ii_provenance",
        lambda _priors, _contracts_path: (
            Path("synthetic/phase_iii_census_sbir_awards.parquet"),
            Path("synthetic/phase_ii_awards.parquet"),
        ),
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
        "sbir_awards_path",
        "phase_ii_awards_path",
        "census_data_cut_date",
        "frozen_spec_commit",
        "ordered_clauses",
        "reproducibility",
    }
    assert census_assets.FROZEN_SPEC_COMMIT == ("6d81874eaf6345abb32d116bfef40f8838a97bb4")
    assert not any(
        token in key.lower()
        for key in metadata_keys
        for token in ("headline", "selected_cell", "preferred_cell")
    )
