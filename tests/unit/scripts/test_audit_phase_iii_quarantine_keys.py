import json

import pandas as pd
import pytest

from sbir_analytics.assets.phase_iii_negative_controls.identity import (
    IdentityRecoveryError,
    RecoveryStatus,
)
from scripts.data.audit_phase_iii_quarantine_keys import run


pytestmark = pytest.mark.fast


def test_failed_gate_persists_auditable_artifacts_before_stopping(tmp_path) -> None:
    fingerprint = "a" * 64
    input_path = tmp_path / "sbir.parquet"
    recovery_path = tmp_path / "recovery.parquet"
    output_dir = tmp_path / "identity"
    pd.DataFrame(
        [
            {
                "source_row_sha256": fingerprint,
                "company_name": None,
                "state": None,
                "address1": None,
                "address2": None,
                "zip": None,
            }
        ]
    ).to_parquet(input_path, index=False)
    pd.DataFrame(
        [
            {
                "source_row_sha256": fingerprint,
                "recovery_status": RecoveryStatus.UNRESOLVED_NO_MATCH.value,
                "agency": "Department of Defense",
                "award_year": "2020",
            }
        ]
    ).to_parquet(recovery_path, index=False)

    with pytest.raises(IdentityRecoveryError, match="quarantine-key gate failed"):
        run(input_path, recovery_path, output_dir)

    audit_path = output_dir / "phase_iii_identity_quarantine_key_audit.parquet"
    coverage_path = output_dir / "phase_iii_identity_quarantine_key_coverage.parquet"
    summary_path = output_dir / "phase_iii_identity_quarantine_key_coverage.json"
    assert audit_path.is_file()
    assert coverage_path.is_file()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["gate"] == {
        "passed": False,
        "unquarantinable_source_rows": 1,
        "unresolved_source_rows": 1,
    }
    assert summary["coverage_category_counts"] == {
        "address_zip_only": 0,
        "both": 0,
        "name_state_only": 0,
        "neither": 1,
    }
    assert summary["source_fingerprint_continuity"] == {
        "exact_source_row_matches": 1,
        "missing_source_row_matches": 0,
        "recovery_audit_source_rows": 1,
    }
    assert summary["control_candidate_rows_read"] == 0
