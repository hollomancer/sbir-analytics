"""Tests for the exact-UEI Phase III control contract-extraction frame."""

import importlib.util
import json
from pathlib import Path

import pandas as pd


SCRIPT = Path(__file__).parents[3] / "scripts/data/build_phase_iii_control_vendor_filters.py"
SPEC = importlib.util.spec_from_file_location("build_phase_iii_control_vendor_filters", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_vendor_filter_contains_only_exact_control_and_phase_ii_ueis(tmp_path: Path) -> None:
    eligibility_path = tmp_path / "eligibility.parquet"
    phase_ii_path = tmp_path / "phase_ii.parquet"
    output_path = tmp_path / "filters.json"
    pd.DataFrame(
        {
            "candidate_envelope_id": ["ELIGIBLE", "POSITIVE", "INDETERMINATE"],
            "eligibility_status": [
                "eligible_screened_negative",
                "confirmed_sbir",
                "indeterminate_possible_sbir",
            ],
            "candidate_ueis": [
                ("CONTROLUEI01", "CONTROLUEI02"),
                ("POSITIVEUEI1",),
                ("UNKNOWNUEI01",),
            ],
            "name_state_keys": [("CONTROL LLC|VA",), (), ()],
            "address_zip_keys": [("1 MAIN ST|22030",), (), ()],
            "sam_source_rows": [1, 1, 1],
            "multiple_ueis": [True, False, False],
            "multiple_duns": [False, False, False],
            "multiple_cages": [False, False, False],
        }
    ).to_parquet(eligibility_path, index=False)
    pd.DataFrame(
        {"recipient_uei": ["TREATEDUEI01", None, "TREATEDUEI02", "TREATEDUEI01"]}
    ).to_parquet(phase_ii_path, index=False)
    module._write_json_atomic(
        phase_ii_path.with_suffix(".checks.json"),
        {
            "schema_version": "phase-ii-awards-v2",
            "ok": True,
            "output": {"sha256": module._file_sha256(phase_ii_path)},
        },
    )

    result = module.run(eligibility_path, phase_ii_path, output_path)

    filters = json.loads(output_path.read_text())
    assert filters == {
        "company_names": [],
        "duns": [],
        "uei": ["CONTROLUEI01", "CONTROLUEI02", "TREATEDUEI01", "TREATEDUEI02"],
    }
    assert result["counts"] == {
        "eligible_control_envelopes": 1,
        "eligible_control_ueis": 2,
        "phase_ii_treated_ueis": 2,
        "combined_unique_ueis": 4,
    }
    assert result["output"]["identifier_methods"] == ["uei_exact"]
