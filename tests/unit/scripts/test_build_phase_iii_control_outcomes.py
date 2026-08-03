"""Focused tests for the Phase III negative-control outcome materializer."""

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

from sbir_analytics.assets.phase_iii_census.criteria import CensusInputError


SCRIPT = Path(__file__).parents[3] / "scripts/data/build_phase_iii_control_outcomes.py"
SPEC = importlib.util.spec_from_file_location("build_phase_iii_control_outcomes", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _contract(uei: str, row_id: int) -> dict[str, object]:
    return {
        "contract_id": f"PIID-{row_id}",
        "piid": f"PIID-{row_id}",
        "transaction_unique_id": f"TX-{row_id}",
        "generated_unique_award_id": f"AWARD-{row_id}",
        "agency": "DEPARTMENT A",
        "sub_agency": "COMPONENT A",
        "vendor_uei": uei,
        "action_date": "2021-01-01",
        "obligation_amount": 100.0,
        "competition_type": "FULL AND OPEN COMPETITION",
        "description": "Research services",
        "research": None,
        "naics_code": "541715",
        "product_or_service_code": "AC13",
    }


def test_load_contract_rows_projects_only_matched_exact_ueis(tmp_path: Path) -> None:
    path = tmp_path / "contracts.parquet"
    pd.DataFrame(
        [
            _contract("AAAAAAAAAAAA", 1),
            _contract("BBBBBBBBBBBB", 2),
            _contract("CCCCCCCCCCCC", 3),
        ]
    ).to_parquet(path, index=False)

    selected = MODULE._load_contract_rows(path, {"AAAAAAAAAAAA", "CCCCCCCCCCCC"})

    assert selected.columns.tolist() == list(MODULE.CENSUS_CONTRACT_COLUMNS)
    assert set(selected["vendor_uei"]) == {"AAAAAAAAAAAA", "CCCCCCCCCCCC"}


def test_audit_totals_preserve_firm_denominators_and_separate_grains() -> None:
    firm_counts = pd.DataFrame(
        [
            {
                "arm": "sbir",
                "firm_id": "S1",
                "step_order": 0,
                "clause_id": "all_exact_uei_pairs",
                "clause": "all",
                "surviving_pairs": 3,
                "distinct_transactions": 2,
                "distinct_contracts": 1,
            },
            {
                "arm": "sbir",
                "firm_id": "S2",
                "step_order": 0,
                "clause_id": "all_exact_uei_pairs",
                "clause": "all",
                "surviving_pairs": 0,
                "distinct_transactions": 0,
                "distinct_contracts": 0,
            },
        ]
    )

    assert MODULE._audit_totals(firm_counts).to_dict(orient="records") == [
        {
            "arm": "sbir",
            "step_order": 0,
            "clause_id": "all_exact_uei_pairs",
            "clause": "all",
            "surviving_pairs": 3,
            "distinct_transactions": 2,
            "firm_contract_instances": 1,
            "firms": 2,
        }
    ]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("pre_outcome_only", False),
        ("census_filter_invoked", True),
        ("stochastic", True),
        ("balance_passed", False),
    ],
)
def test_load_matching_inputs_enforces_pre_outcome_manifest_gates(
    tmp_path: Path, field: str, value: bool
) -> None:
    manifest = {
        "schema_version": "phase-iii-control-matching-v1",
        "pre_outcome_only": True,
        "census_filter_invoked": False,
        "stochastic": False,
        "balance_passed": True,
        "artifacts": {},
    }
    manifest[field] = value
    manifest_path = tmp_path / "matching.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(CensusInputError, match="does not authorize outcome inputs"):
        MODULE._load_matching_inputs(tmp_path, manifest_path)


def test_load_matching_inputs_rejects_bad_artifact_schema_and_row_count(
    tmp_path: Path,
) -> None:
    frames = {
        "treated_covariates": pd.DataFrame([{"firm_id": "T1", "firm_ueis": ("AAAAAAAAAAAA",)}]),
        "control_covariates": pd.DataFrame([{"firm_id": "C1", "firm_ueis": ("BBBBBBBBBBBB",)}]),
        "coverage": pd.DataFrame(
            [
                {
                    "arm": "sbir",
                    "covariate": "primary_naics",
                    "observed_firms": 1,
                    "missing_firms": 0,
                    "conflict_firms": 0,
                    "total_firms": 1,
                }
            ]
        ),
        "matches": pd.DataFrame([{"treated_firm_id": "T1", "control_firm_id": "C1"}]),
        "matching_summary": pd.DataFrame([{"matched_control_count": 1, "treated_firms": 1}]),
        "balance": pd.DataFrame(
            [
                {
                    "covariate": "primary_naics",
                    "level": "541715",
                    "treated_value": 1.0,
                    "control_value": 1.0,
                    "standardized_mean_difference": 0.0,
                    "absolute_smd": 0.0,
                    "flagged_above_0_1": False,
                }
            ]
        ),
    }
    artifacts = {}
    for label, filename in MODULE.MATCHING_ARTIFACTS.items():
        path = tmp_path / filename
        frames[label].to_parquet(path, index=False)
        artifacts[label] = {
            "path": str(path),
            "sha256": MODULE._file_sha256(path),
            "rows": len(frames[label]),
        }
    manifest = {
        "schema_version": "phase-iii-control-matching-v1",
        "pre_outcome_only": True,
        "census_filter_invoked": False,
        "stochastic": False,
        "balance_passed": True,
        "artifacts": artifacts,
    }
    manifest_path = tmp_path / "matching.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(CensusInputError, match="matches artifact is missing required columns"):
        MODULE._load_matching_inputs(tmp_path, manifest_path)

    matches_path = tmp_path / MODULE.MATCHING_ARTIFACTS["matches"]
    frames["matches"].assign(control_slot=1).to_parquet(matches_path, index=False)
    manifest["artifacts"]["matches"]["sha256"] = MODULE._file_sha256(matches_path)
    manifest["artifacts"]["matches"]["rows"] = 2
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(CensusInputError, match="matches row count differs"):
        MODULE._load_matching_inputs(tmp_path, manifest_path)
