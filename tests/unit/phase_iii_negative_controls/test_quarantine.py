import pandas as pd
import pytest

from sbir_analytics.assets.phase_iii_negative_controls.identity import (
    IdentityRecoveryError,
    RecoveryStatus,
)
from sbir_analytics.assets.phase_iii_negative_controls.quarantine import (
    QuarantineKeyCoverage,
    build_unresolved_quarantine_key_audit,
    normalize_quarantine_component,
    normalize_zip5,
    quarantine_key_gate,
    require_complete_unresolved_quarantine_keys,
    summarize_quarantine_key_coverage,
)


pytestmark = pytest.mark.fast


def _source(
    fingerprint: str,
    *,
    company: object = "Example, LLC",
    state: object = "VA",
    address1: object = "100 Main St.",
    address2: object = "Suite #2",
    zip_code: object = "01234-5678",
) -> dict[str, object]:
    return {
        "source_row_sha256": fingerprint,
        "company_name": company,
        "state": state,
        "address1": address1,
        "address2": address2,
        "zip": zip_code,
    }


def _recovery(
    fingerprint: str,
    status: RecoveryStatus = RecoveryStatus.UNRESOLVED_NO_MATCH,
) -> dict[str, object]:
    return {
        "source_row_sha256": fingerprint,
        "recovery_status": status.value,
        "agency": "Department of Defense",
        "award_year": "2020",
        "attempted_adapters": ("usaspending_piid",),
    }


def test_frozen_component_and_zip_normalization() -> None:
    assert normalize_quarantine_component("  Acme, L.L.C.  ") == "ACME L L C"
    assert normalize_quarantine_component("１２３ Main—Street") == "123 MAIN STREET"
    assert normalize_zip5("01234") == "01234"
    assert normalize_zip5("01234-5678") == "01234"
    assert normalize_zip5("01234 5678") == "01234"
    assert normalize_zip5("012345678") == "01234"
    assert normalize_zip5("1234") == ""
    assert normalize_zip5("01234-567") == ""


def test_audit_reports_all_four_categories_and_excludes_resolved_rows() -> None:
    fingerprints = [character * 64 for character in "abcde"]
    source = pd.DataFrame(
        [
            _source(fingerprints[0]),
            _source(fingerprints[1], address1=None, address2=None, zip_code=None),
            _source(fingerprints[2], company=None, state=None),
            _source(
                fingerprints[3],
                company=None,
                state=None,
                address1=None,
                address2=None,
                zip_code=None,
            ),
            _source(fingerprints[4]),
        ]
    )
    recovery = pd.DataFrame(
        [
            _recovery(fingerprints[0]),
            _recovery(fingerprints[1]),
            _recovery(fingerprints[2]),
            _recovery(fingerprints[3]),
            _recovery(fingerprints[4], RecoveryStatus.RESOLVED_AUTHORITATIVE),
        ]
    )

    audit = build_unresolved_quarantine_key_audit(source, recovery)

    assert audit["coverage_category"].tolist() == [
        QuarantineKeyCoverage.BOTH,
        QuarantineKeyCoverage.NAME_STATE_ONLY,
        QuarantineKeyCoverage.ADDRESS_ZIP_ONLY,
        QuarantineKeyCoverage.NEITHER,
    ]
    assert audit.loc[0, "name_state_key"] == "EXAMPLE LLC|VA"
    assert audit.loc[0, "address_zip_key"] == "100 MAIN ST SUITE 2|01234"
    assert fingerprints[4] not in set(audit["source_row_sha256"])

    summary = summarize_quarantine_key_coverage(audit)
    assert summary["coverage_category"].tolist() == [
        "both",
        "name_state_only",
        "address_zip_only",
        "neither",
    ]
    assert summary["source_rows"].tolist() == [1, 1, 1, 1]


def test_blank_component_never_forms_a_partial_key() -> None:
    fingerprint = "a" * 64
    audit = build_unresolved_quarantine_key_audit(
        pd.DataFrame(
            [
                _source(
                    fingerprint,
                    state=" ",
                    address1="100 Main St",
                    address2=None,
                    zip_code="not-a-zip",
                )
            ]
        ),
        pd.DataFrame([_recovery(fingerprint)]),
    )

    row = audit.iloc[0]
    assert row["company_name_key"] == "EXAMPLE LLC"
    assert row["name_state_key"] is None
    assert row["address_zip_key"] is None
    assert row["coverage_category"] == QuarantineKeyCoverage.NEITHER


def test_gate_has_no_allowable_neither_share() -> None:
    fingerprint = "a" * 64
    audit = build_unresolved_quarantine_key_audit(
        pd.DataFrame(
            [
                _source(
                    fingerprint,
                    company=None,
                    state=None,
                    address1=None,
                    address2=None,
                    zip_code=None,
                )
            ]
        ),
        pd.DataFrame([_recovery(fingerprint)]),
    )

    assert quarantine_key_gate(audit) == {
        "passed": False,
        "unresolved_source_rows": 1,
        "unquarantinable_source_rows": 1,
    }
    with pytest.raises(IdentityRecoveryError, match="1 source rows have neither"):
        require_complete_unresolved_quarantine_keys(audit)


def test_gate_passes_when_every_unresolved_row_has_either_key() -> None:
    fingerprint = "a" * 64
    audit = build_unresolved_quarantine_key_audit(
        pd.DataFrame([_source(fingerprint, address1=None, address2=None, zip_code=None)]),
        pd.DataFrame([_recovery(fingerprint)]),
    )

    require_complete_unresolved_quarantine_keys(audit)
    assert quarantine_key_gate(audit)["passed"] is True


@pytest.mark.parametrize("target", ["source", "recovery"])
def test_audit_rejects_duplicate_fingerprints(target: str) -> None:
    fingerprint = "a" * 64
    source = pd.DataFrame([_source(fingerprint)])
    recovery = pd.DataFrame([_recovery(fingerprint)])
    if target == "source":
        source = pd.concat([source, source], ignore_index=True)
    else:
        recovery = pd.concat([recovery, recovery], ignore_index=True)

    with pytest.raises(IdentityRecoveryError, match="values must be unique"):
        build_unresolved_quarantine_key_audit(source, recovery)


def test_audit_rejects_recovery_row_missing_from_source() -> None:
    with pytest.raises(IdentityRecoveryError, match="absent from the SBIR source"):
        build_unresolved_quarantine_key_audit(
            pd.DataFrame([_source("a" * 64)]),
            pd.DataFrame([_recovery("b" * 64)]),
        )
