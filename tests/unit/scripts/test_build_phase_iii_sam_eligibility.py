"""Tests for SAM eligibility artifact materialization."""

import json

import pandas as pd
import pytest

from sbir_analytics.assets.phase_iii_negative_controls import IdentityRecoveryError
from scripts.data.build_phase_iii_sam_eligibility import run


def _write_inputs(tmp_path, *, reliable: bool):
    sam = pd.DataFrame(
        {
            "unique_entity_id": ["DIRECTUEI001"],
            "duns_number": [None],
            "cage_code": ["A1B2C"],
            "legal_business_name": ["Exact Candidate LLC" if reliable else ""],
            "dba_name": [None],
            "physical_address_line_1": ["10 Exact Road" if reliable else ""],
            "physical_address_line_2": [None],
            "physical_address_state": ["VA" if reliable else ""],
            "physical_address_zip_postal_code": ["22030" if reliable else ""],
        }
    )
    source = pd.DataFrame(
        {
            "source_row_sha256": ["a" * 64],
            "uei": ["DIRECTUEI001"],
            "duns": [None],
        }
    )
    recovery = pd.DataFrame(
        columns=["source_row_sha256", "recovery_status", "resolved_ueis", "resolved_duns"]
    )
    quarantine = pd.DataFrame(
        columns=[
            "source_row_sha256",
            "name_state_key",
            "address_zip_key",
            "has_name_state_key",
            "has_address_zip_key",
            "coverage_category",
        ]
    )
    paths = {}
    for name, frame in (
        ("sam", sam),
        ("source", source),
        ("recovery", recovery),
        ("quarantine", quarantine),
    ):
        path = tmp_path / f"{name}.parquet"
        frame.to_parquet(path, index=False)
        paths[name] = path
    return paths


def test_run_writes_all_three_statuses_and_provenance(tmp_path) -> None:
    paths = _write_inputs(tmp_path, reliable=True)
    output_dir = tmp_path / "output"

    summary = run(
        paths["sam"],
        paths["source"],
        paths["recovery"],
        paths["quarantine"],
        output_dir,
    )

    assert summary["gate"]["passed"] is True
    statuses = pd.read_parquet(output_dir / "phase_iii_sam_eligibility_statuses.parquet")
    assert statuses["eligibility_status"].tolist() == [
        "confirmed_sbir",
        "indeterminate_possible_sbir",
        "eligible_screened_negative",
    ]
    assert statuses["candidate_firms"].tolist() == [1, 0, 0]
    persisted = json.loads((output_dir / "phase_iii_sam_eligibility.json").read_text())
    assert persisted["matching_rows_read"] == 0
    assert persisted["outcome_rows_read"] == 0


def test_run_writes_audit_artifacts_before_failing_reliability_gate(tmp_path) -> None:
    paths = _write_inputs(tmp_path, reliable=False)
    output_dir = tmp_path / "output"

    with pytest.raises(IdentityRecoveryError, match="eligibility is unreliable"):
        run(
            paths["sam"],
            paths["source"],
            paths["recovery"],
            paths["quarantine"],
            output_dir,
        )

    assert (output_dir / "phase_iii_sam_eligibility.parquet").is_file()
    persisted = json.loads((output_dir / "phase_iii_sam_eligibility.json").read_text())
    assert persisted["gate"]["passed"] is False
    assert persisted["gate"]["candidate_firms_without_quarantine_key"] == 1
