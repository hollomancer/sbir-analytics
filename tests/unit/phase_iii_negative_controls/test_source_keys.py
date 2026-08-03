import pandas as pd
import pytest

from sbir_analytics.assets.phase_iii_negative_controls.identity import (
    IdentityRecoveryError,
    RecoveryStatus,
    resolve_award_identities,
)
from sbir_analytics.assets.phase_iii_negative_controls.source_keys import (
    NIH_PROJECT_ADAPTER,
    USA_FAIN_ADAPTER,
    USA_PIID_ADAPTER,
    USA_URI_ADAPTER,
    build_nih_official_keys,
    build_nih_sbir_attempts,
    build_usaspending_official_keys,
    build_usaspending_sbir_attempts,
    canonicalize_nih_project_number,
    canonicalize_piid,
)


pytestmark = pytest.mark.fast


def test_usaspending_key_expansion_is_exact_and_uses_no_name_fields() -> None:
    sbir = pd.DataFrame(
        [
            {
                "source_row_sha256": "a" * 64,
                "agency": "Department of Defense",
                "contract": " FA-12-34 ",
                "agency_tracking_number": None,
                "company_name": "Name Does Not Participate LLC",
            }
        ]
    )
    official = pd.DataFrame(
        [
            {
                "official_record_id": "OFFICIAL-1",
                "awarding_agency": "Department of Defense",
                "piid": "FA1234",
                "fain": None,
                "uri": None,
                "recipient_uei": "UEI000000001",
                "recipient_duns": "123456789",
                "recipient_name": "Completely Different Name Inc",
            }
        ]
    )

    attempts = build_usaspending_sbir_attempts(sbir)
    keys = build_usaspending_official_keys(
        official,
        source_digest="b" * 64,
        snapshot_date="2026-02-06",
    )
    result = resolve_award_identities(attempts, keys)

    assert attempts["adapter"].tolist() == [
        USA_PIID_ADAPTER,
        USA_FAIN_ADAPTER,
        USA_URI_ADAPTER,
    ]
    assert result["recovery_status"].tolist() == [
        RecoveryStatus.RESOLVED_AUTHORITATIVE,
        RecoveryStatus.UNRESOLVED_NO_MATCH,
        RecoveryStatus.UNRESOLVED_NO_MATCH,
    ]


def test_usaspending_attempts_include_both_declared_source_key_fields() -> None:
    sbir = pd.DataFrame(
        [
            {
                "source_row_sha256": "a" * 64,
                "agency": "Department of Defense",
                "contract": "FA-12-34",
                "agency_tracking_number": "TRACK-5678",
            }
        ]
    )

    attempts = build_usaspending_sbir_attempts(sbir)

    assert len(attempts) == 6
    assert set(attempts["source_key_field"]) == {"contract", "agency_tracking_number"}
    assert attempts["recovery_attempt_id"].is_unique


def test_usaspending_fain_and_uri_preserve_internal_punctuation() -> None:
    official = pd.DataFrame(
        [
            {
                "official_record_id": "OFFICIAL-1",
                "awarding_agency": "National Science Foundation",
                "piid": None,
                "fain": "ABC-123",
                "uri": "URI/ABC-123",
                "recipient_uei": "UEI000000001",
                "recipient_duns": None,
            }
        ]
    )

    keys = build_usaspending_official_keys(
        official,
        source_digest="b" * 64,
        snapshot_date="2026-02-06",
    ).set_index("adapter")

    assert keys.loc[USA_FAIN_ADAPTER, "canonical_award_key"] == "ABC-123"
    assert keys.loc[USA_URI_ADAPTER, "canonical_award_key"] == "URI/ABC-123"


def test_nih_project_adapter_normalizes_structured_project_number() -> None:
    assert canonicalize_nih_project_number(" 1 N43 AA42005-00, ") == "1N43AA4200500"
    assert canonicalize_piid(" FA-12 34 ") == "FA1234"

    sbir = pd.DataFrame(
        [
            {
                "source_row_sha256": "a" * 64,
                "agency": "Department of Health and Human Services",
                "contract": "1 N43 AA42005-00,",
                "agency_tracking_number": None,
                "award_year": "2001",
            }
        ]
    )
    official = pd.DataFrame(
        [
            {
                "official_record_id": "NIH-1",
                "project_num": "1N43AA42005-00",
                "core_project_num": "N43AA42005",
                "fiscal_year": 2001,
                "recipient_uei": "UEI000000001",
                "recipient_duns": "123456789",
            }
        ]
    )

    attempts = build_nih_sbir_attempts(sbir)
    keys = build_nih_official_keys(
        official,
        source_digest="c" * 64,
        snapshot_date="2026-08-03",
    )
    result = resolve_award_identities(attempts, keys)

    assert attempts.loc[0, "adapter"] == NIH_PROJECT_ADAPTER
    assert result.loc[0, "recovery_status"] == RecoveryStatus.RESOLVED_AUTHORITATIVE


def test_nih_adapter_rejects_missing_year_instead_of_relaxing_join() -> None:
    sbir = pd.DataFrame(
        [
            {
                "source_row_sha256": "a" * 64,
                "agency": "Department of Health and Human Services",
                "contract": "1N43AA42005-00",
                "agency_tracking_number": None,
                "award_year": None,
            }
        ]
    )

    with pytest.raises(IdentityRecoveryError, match="four-digit award year"):
        build_nih_sbir_attempts(sbir)
