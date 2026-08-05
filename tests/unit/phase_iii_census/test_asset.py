import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest
import yaml
from dagster import AssetCheckResult, Output, build_asset_context

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
                "agency": "DEPARTMENT A",
                "sub_agency": "COMPONENT A",
                "naics_code": "541715",
                "product_or_service_code": "AC13",
                "description": "Follow-on work",
                "action_date": "2021-01-01",
                "competition_type": "FULL AND OPEN COMPETITION",
                "obligation_amount": -25,
                "research": None,
                "transaction_unique_id": "TRANSACTION-1",
                "generated_unique_award_id": "GENERATED-AWARD-1",
                "piid": "PIID-1",
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


def test_frozen_spec_verification_hashes_exact_raw_bytes() -> None:
    record = census_assets.verify_frozen_spec()

    assert record == {
        "revision": "phase-0-r15",
        "spec_path": "specs/phase-iii-census/design.md",
        "spec_sha256": census_assets.FROZEN_SPEC_SHA256,
        "amendments_path": "specs/phase-iii-census/amendments.md",
        "amendments_sha256": census_assets.AMENDMENTS_LOG_SHA256,
    }
    assert hashlib.sha256(census_assets.FROZEN_SPEC_PATH.read_bytes()).hexdigest() == (
        census_assets.FROZEN_SPEC_SHA256
    )
    assert hashlib.sha256(census_assets.AMENDMENTS_LOG_PATH.read_bytes()).hexdigest() == (
        census_assets.AMENDMENTS_LOG_SHA256
    )


def test_materialization_gate_matches_authorized_repository_manifest() -> None:
    assert census_assets.verify_materialization_gate() == {
        "study_id": "phase-iii-census",
        "evidence_status": "reproducible",
        "materialization_allowed": True,
        "manifest_path": "studies/phase-iii-census/study.yaml",
    }


def test_closed_materialization_gate_stops_before_loading_sources(
    tmp_path: Path, monkeypatch
) -> None:
    manifest = yaml.safe_load(census_assets.STUDY_MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["materialization"] = {
        "allowed": False,
        "blockers": ["Negative-control eligibility is unresolved."],
    }
    manifest_path = tmp_path / "study.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    loader_called = False

    def unexpected_loader():
        nonlocal loader_called
        loader_called = True
        raise AssertionError("source loader must not run while the study gate is closed")

    monkeypatch.setattr(census_assets, "STUDY_MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(census_assets, "_load_contracts", unexpected_loader)

    with pytest.raises(CensusInputError, match="materialization blocked.*Negative-control"):
        census_assets.phase_iii_census(build_asset_context(), _prior_source())

    assert not loader_called


def test_asset_fails_on_spec_mismatch_before_loading_any_source(
    tmp_path: Path, monkeypatch
) -> None:
    changed_spec = tmp_path / "design.md"
    changed_spec.write_bytes(census_assets.FROZEN_SPEC_PATH.read_bytes() + b"\nchanged\n")
    loader_called = False

    def unexpected_loader():
        nonlocal loader_called
        loader_called = True
        raise AssertionError("source loader must not run after a freeze mismatch")

    monkeypatch.setattr(census_assets, "FROZEN_SPEC_PATH", changed_spec)
    monkeypatch.setattr(census_assets, "_load_contracts", unexpected_loader)

    with pytest.raises(CensusInputError, match="design SHA-256 mismatch"):
        census_assets.phase_iii_census(build_asset_context(), _prior_source())

    assert not loader_called


def test_frozen_spec_verification_fails_closed_on_missing_amendment_log(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(census_assets, "AMENDMENTS_LOG_PATH", tmp_path / "missing.md")

    with pytest.raises(CensusInputError, match="amendment log is missing or unreadable"):
        census_assets.verify_frozen_spec()


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
    pd.testing.assert_frame_equal(
        loaded,
        _contract_source().loc[:, list(census_assets.CENSUS_CONTRACT_COLUMNS)],
    )

    manifest_path = contracts_path.with_suffix(".checks.json")
    manifest_path.write_text("[]", encoding="utf-8")
    with pytest.raises(CensusInputError, match="must be a JSON object"):
        census_assets._load_contracts()

    _write_contract_manifest(contracts_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_provenance"]["provenance_version"] = 0
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(CensusInputError, match="unsupported version"):
        census_assets._load_contracts()

    _write_contract_manifest(contracts_path)
    contracts_path.write_bytes(contracts_path.read_bytes() + b"tampered")
    with pytest.raises(CensusInputError, match="checksum"):
        census_assets._load_contracts()


def test_contract_loader_fails_closed_on_projected_schema_drift(
    tmp_path: Path, monkeypatch
) -> None:
    contracts_path = tmp_path / "contracts.parquet"
    _contract_source().drop(columns="product_or_service_code").to_parquet(contracts_path)
    _write_contract_manifest(contracts_path)
    monkeypatch.setattr(census_assets, "CONTRACTS_PRIMARY_PATH", contracts_path)
    monkeypatch.setattr(census_assets, "CONTRACTS_FALLBACK_PATH", tmp_path / "missing.parquet")

    with pytest.raises(CensusInputError, match="Failed to read contract source"):
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


def test_prior_frame_comparison_accepts_only_parquet_null_representation_changes() -> None:
    persisted = pd.DataFrame(
        {
            "source_row_sha256": pd.Series(["a" * 64, None], dtype="string[pyarrow]"),
            "source_transaction_count": pd.Series([1.0, float("nan")], dtype="float64"),
        }
    )
    in_memory = pd.DataFrame(
        {
            "source_row_sha256": ["a" * 64, float("nan")],
            "source_transaction_count": [1, None],
        },
        dtype=object,
    )

    census_assets._assert_prior_frames_equal(persisted, in_memory)

    substantive_changes = []

    changed_value = in_memory.copy()
    changed_value.loc[0, "source_transaction_count"] = 1.0000001
    substantive_changes.append(changed_value)
    substantive_changes.append(in_memory.iloc[::-1].reset_index(drop=True))
    substantive_changes.append(in_memory.iloc[:, ::-1])

    for changed in substantive_changes:
        with pytest.raises(AssertionError):
            census_assets._assert_prior_frames_equal(persisted, changed)

    changed_text = in_memory.copy()
    changed_text.loc[0, "source_row_sha256"] = "b" * 64
    with pytest.raises(AssertionError):
        census_assets._assert_prior_frames_equal(persisted, changed_text)


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
        "frozen_spec_path",
        "frozen_spec_sha256",
        "frozen_spec_revision",
        "amendments_log_path",
        "amendments_log_sha256",
        "study_manifest_path",
        "study_evidence_status",
        "study_materialization_allowed",
        "ordered_clauses",
        "reproducibility",
    }
    assert result.metadata["frozen_spec_sha256"].text == census_assets.FROZEN_SPEC_SHA256
    assert result.metadata["amendments_log_sha256"].text == census_assets.AMENDMENTS_LOG_SHA256
    assert not any(
        token in key.lower()
        for key in metadata_keys
        for token in ("headline", "selected_cell", "preferred_cell")
    )


def _persist_diagnostic_tables(
    dropoff_path: Path,
    sensitivity_path: Path,
    *,
    window_trigger: bool,
) -> None:
    dropoff = pd.DataFrame(
        {
            "clause_id": [
                "all_exact_uei_pairs",
                "prior_end_observable",
                "target_post_completion",
                "not_phase_i_or_ii_coded",
                "not_phase_iii_coded",
                "exact_naics_or_psc_lineage",
            ],
            "surviving_pairs": [100, 80, 60, 50, 40, 20],
            "distinct_firms": [100, 80, 60, 50, 40, 20],
            "distinct_contracts": [100, 80, 60, 50, 40, 20],
        }
    )
    five_count = 5 if window_trigger else 25
    sensitivity = pd.DataFrame(
        [
            ("none__same_agency", 80, 800),
            ("none__same_department", 100, 1_000),
            ("5y__same_agency", five_count, -50),
            ("5y__same_department", five_count, 50),
            ("10y__same_agency", 40, 400),
            ("10y__same_department", 50, 500),
        ],
        columns=["cell_id", "count", "total_obligated_dollars"],
    )
    for metric in ("surviving_pairs", "distinct_firms", "distinct_contracts"):
        sensitivity[metric] = sensitivity["count"]
    sensitivity = sensitivity.drop(columns="count")
    dropoff.to_parquet(dropoff_path, index=False)
    sensitivity.to_parquet(sensitivity_path, index=False)


@pytest.mark.parametrize(("window_trigger", "expected_passed"), [(False, True), (True, False)])
def test_post_write_asset_check_reads_both_tables_and_reports_all_contrasts(
    tmp_path: Path,
    monkeypatch,
    window_trigger: bool,
    expected_passed: bool,
) -> None:
    dropoff_path = tmp_path / "dropoff.parquet"
    sensitivity_path = tmp_path / "sensitivity.parquet"
    _persist_diagnostic_tables(
        dropoff_path,
        sensitivity_path,
        window_trigger=window_trigger,
    )
    monkeypatch.setattr(census_assets, "DROP_OFF_OUTPUT_PATH", dropoff_path)
    monkeypatch.setattr(census_assets, "SENSITIVITY_OUTPUT_PATH", sensitivity_path)

    result = census_assets.phase_iii_census_one_factor_sensitivity()

    assert isinstance(result, AssetCheckResult)
    assert result.passed is expected_passed
    assert result.metadata["comparison_count"].value == 7
    diagnostics = result.metadata["one_factor_diagnostics"].data
    assert len(diagnostics) == 7
    assert {row["dimension"] for row in diagnostics} == {"window", "agency"}
    assert dropoff_path.is_file()
    assert sensitivity_path.is_file()
