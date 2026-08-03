"""Focused tests for the Phase III negative-control outcome materializer."""

import importlib.util
from pathlib import Path

import pandas as pd


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
