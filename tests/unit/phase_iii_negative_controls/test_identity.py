import pandas as pd
import pytest

from sbir_analytics.assets.phase_iii_negative_controls.identity import (
    IdentityRecoveryError,
    RecoveryStatus,
    reconcile_award_identity_attempts,
    resolve_award_identities,
)


pytestmark = pytest.mark.fast


def _sbir_row(source: str = "a" * 64, award_key: str = "AWARD-1") -> dict[str, str]:
    return {
        "source_row_sha256": source,
        "recovery_attempt_id": f"attempt-{source}-{award_key}",
        "adapter": "usaspending",
        "agency_key": "DOD",
        "award_year_key": "2020",
        "canonical_award_key": award_key,
        "company_name": "Similarity Must Not Matter LLC",
    }


def _official_row(
    record_id: str,
    *,
    award_key: str = "AWARD-1",
    uei: object = "UEI000000001",
    duns: object = "123456789",
) -> dict[str, object]:
    return {
        "adapter": "usaspending",
        "agency_key": "DOD",
        "award_year_key": "2020",
        "canonical_award_key": award_key,
        "official_record_id": record_id,
        "recipient_uei": uei,
        "recipient_duns": duns,
        "source_digest": "b" * 64,
        "snapshot_date": "2026-02-06",
        "recipient_name": "A Name Is Not a Join Key Inc",
    }


def test_exact_award_key_resolves_one_authoritative_identity_with_provenance() -> None:
    result = resolve_award_identities(
        pd.DataFrame([_sbir_row()]),
        pd.DataFrame([_official_row("OFFICIAL-1")]),
    )

    row = result.iloc[0]
    assert row["recovery_status"] == RecoveryStatus.RESOLVED_AUTHORITATIVE
    assert row["resolved_ueis"] == ("UEI000000001",)
    assert row["resolved_duns"] == ("123456789",)
    assert row["official_record_ids"] == ("OFFICIAL-1",)
    assert row["official_source_digests"] == ("b" * 64,)
    assert row["official_snapshot_dates"] == ("2026-02-06",)


def test_connected_uei_and_duns_records_remain_one_identity() -> None:
    official = pd.DataFrame(
        [
            _official_row("UEI-AND-DUNS"),
            _official_row("DUNS-ONLY", uei=None),
        ]
    )

    result = resolve_award_identities(pd.DataFrame([_sbir_row()]), official)

    assert result.loc[0, "recovery_status"] == RecoveryStatus.RESOLVED_AUTHORITATIVE
    assert result.loc[0, "official_record_ids"] == ("DUNS-ONLY", "UEI-AND-DUNS")


def test_disconnected_recipient_identifiers_are_quarantined_as_conflict() -> None:
    official = pd.DataFrame(
        [
            _official_row("RECIPIENT-1"),
            _official_row(
                "RECIPIENT-2",
                uei="UEI000000002",
                duns="987654321",
            ),
        ]
    )

    result = resolve_award_identities(pd.DataFrame([_sbir_row()]), official)

    assert result.loc[0, "recovery_status"] == RecoveryStatus.UNRESOLVED_CONFLICT
    assert result.loc[0, "resolved_ueis"] == ()
    assert result.loc[0, "resolved_duns"] == ()


def test_missing_official_identifier_and_no_match_have_distinct_statuses() -> None:
    sbir = pd.DataFrame(
        [
            _sbir_row(source="a" * 64, award_key="MISSING-ID"),
            _sbir_row(source="c" * 64, award_key="NO-MATCH"),
        ]
    )
    official = pd.DataFrame(
        [_official_row("MISSING-ID-ROW", award_key="MISSING-ID", uei=None, duns=None)]
    )

    result = resolve_award_identities(sbir, official)

    assert result["recovery_status"].tolist() == [
        RecoveryStatus.UNRESOLVED_MISSING_IDENTIFIER,
        RecoveryStatus.UNRESOLVED_NO_MATCH,
    ]


def test_company_names_cannot_create_a_match() -> None:
    sbir = pd.DataFrame([_sbir_row(award_key="SBIR-KEY")])
    official = pd.DataFrame([_official_row("OTHER", award_key="OTHER-KEY")])
    official.loc[0, "recipient_name"] = sbir.loc[0, "company_name"]

    result = resolve_award_identities(sbir, official)

    assert result.loc[0, "recovery_status"] == RecoveryStatus.UNRESOLVED_NO_MATCH


def test_recovery_preserves_source_order_and_columns() -> None:
    sbir = pd.DataFrame(
        [
            _sbir_row(source="c" * 64, award_key="NO-MATCH"),
            _sbir_row(source="a" * 64, award_key="AWARD-1"),
        ],
        index=[41, 9],
    )

    result = resolve_award_identities(sbir, pd.DataFrame([_official_row("OFFICIAL-1")]))

    assert result["source_row_sha256"].tolist() == ["c" * 64, "a" * 64]
    assert result["company_name"].tolist() == [
        "Similarity Must Not Matter LLC",
        "Similarity Must Not Matter LLC",
    ]


@pytest.mark.parametrize(
    ("target", "column", "message"),
    [
        ("sbir", "canonical_award_key", "SBIR recovery frame.canonical_award_key"),
        ("official", "source_digest", "official award frame.source_digest"),
    ],
)
def test_recovery_rejects_blank_keys_and_provenance(
    target: str,
    column: str,
    message: str,
) -> None:
    sbir = pd.DataFrame([_sbir_row()])
    official = pd.DataFrame([_official_row("OFFICIAL-1")])
    (sbir if target == "sbir" else official).loc[0, column] = " "

    with pytest.raises(IdentityRecoveryError, match=message):
        resolve_award_identities(sbir, official)


def test_recovery_rejects_duplicate_attempt_ids() -> None:
    sbir = pd.DataFrame([_sbir_row(), _sbir_row()])

    with pytest.raises(IdentityRecoveryError, match="recovery_attempt_id values must be unique"):
        resolve_award_identities(sbir, pd.DataFrame([_official_row("OFFICIAL-1")]))


def _attempt_audit(
    adapter: str,
    status: RecoveryStatus,
    *,
    source: str = "a" * 64,
    ueis: tuple[str, ...] = (),
    duns_values: tuple[str, ...] = (),
) -> dict[str, object]:
    has_match = status != RecoveryStatus.UNRESOLVED_NO_MATCH
    return {
        "source_row_sha256": source,
        "adapter": adapter,
        "recovery_status": status.value,
        "resolved_ueis": ueis,
        "resolved_duns": duns_values,
        "official_record_ids": (f"OFFICIAL-{adapter}",) if has_match else (),
        "official_source_digests": ("b" * 64,) if has_match else (),
        "official_snapshot_dates": ("2026-02-06",) if has_match else (),
    }


def test_reconciliation_keeps_one_resolution_and_records_all_attempts() -> None:
    attempts = pd.DataFrame(
        [
            _attempt_audit(
                "usaspending_piid",
                RecoveryStatus.RESOLVED_AUTHORITATIVE,
                ueis=("UEI000000001",),
                duns_values=("123456789",),
            ),
            _attempt_audit("usaspending_fain", RecoveryStatus.UNRESOLVED_NO_MATCH),
            _attempt_audit("usaspending_uri", RecoveryStatus.UNRESOLVED_NO_MATCH),
        ]
    )

    result = reconcile_award_identity_attempts(attempts)

    assert result.loc[0, "recovery_status"] == RecoveryStatus.RESOLVED_AUTHORITATIVE
    assert result.loc[0, "resolved_ueis"] == ("UEI000000001",)
    assert result.loc[0, "attempted_adapters"] == (
        "usaspending_fain",
        "usaspending_piid",
        "usaspending_uri",
    )


def test_reconciliation_accepts_connected_exact_matches() -> None:
    attempts = pd.DataFrame(
        [
            _attempt_audit(
                "usaspending_piid",
                RecoveryStatus.RESOLVED_AUTHORITATIVE,
                ueis=("UEI000000001",),
                duns_values=("123456789",),
            ),
            _attempt_audit(
                "nih_reporter_project_num",
                RecoveryStatus.RESOLVED_AUTHORITATIVE,
                ueis=("UEI000000001",),
            ),
        ]
    )

    result = reconcile_award_identity_attempts(attempts)

    assert result.loc[0, "recovery_status"] == RecoveryStatus.RESOLVED_AUTHORITATIVE
    assert result.loc[0, "resolved_ueis"] == ("UEI000000001",)
    assert result.loc[0, "resolved_duns"] == ("123456789",)


def test_reconciliation_quarantines_disconnected_exact_matches() -> None:
    attempts = pd.DataFrame(
        [
            _attempt_audit(
                "usaspending_piid",
                RecoveryStatus.RESOLVED_AUTHORITATIVE,
                ueis=("UEI000000001",),
            ),
            _attempt_audit(
                "usaspending_fain",
                RecoveryStatus.RESOLVED_AUTHORITATIVE,
                ueis=("UEI000000002",),
            ),
        ]
    )

    result = reconcile_award_identity_attempts(attempts)

    assert result.loc[0, "recovery_status"] == RecoveryStatus.UNRESOLVED_CONFLICT
    assert result.loc[0, "resolved_ueis"] == ()


def test_reconciliation_quarantines_resolution_with_identifierless_match() -> None:
    attempts = pd.DataFrame(
        [
            _attempt_audit(
                "usaspending_piid",
                RecoveryStatus.RESOLVED_AUTHORITATIVE,
                ueis=("UEI000000001",),
            ),
            _attempt_audit(
                "usaspending_fain",
                RecoveryStatus.UNRESOLVED_MISSING_IDENTIFIER,
            ),
        ]
    )

    result = reconcile_award_identity_attempts(attempts)

    assert result.loc[0, "recovery_status"] == RecoveryStatus.UNRESOLVED_CONFLICT


def test_reconciliation_accepts_parquet_list_round_trip(tmp_path) -> None:
    attempts = pd.DataFrame(
        [
            _attempt_audit(
                "usaspending_piid",
                RecoveryStatus.RESOLVED_AUTHORITATIVE,
                ueis=("UEI000000001",),
                duns_values=("123456789",),
            )
        ]
    )
    path = tmp_path / "attempts.parquet"
    attempts.to_parquet(path, index=False)

    result = reconcile_award_identity_attempts(pd.read_parquet(path))

    assert result.loc[0, "recovery_status"] == RecoveryStatus.RESOLVED_AUTHORITATIVE
    assert result.loc[0, "resolved_ueis"] == ("UEI000000001",)
