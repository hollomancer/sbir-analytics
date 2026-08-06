from sbir_analytics.assets.phase_iii_negative_controls import identity as compatibility
from sbir_etl.identity import exact_awards


def test_study_package_reexports_the_promoted_primitive() -> None:
    assert compatibility.resolve_award_identities is exact_awards.resolve_award_identities
    assert (
        compatibility.reconcile_award_identity_attempts
        is exact_awards.reconcile_award_identity_attempts
    )
    assert compatibility.RecoveryStatus is exact_awards.RecoveryStatus
