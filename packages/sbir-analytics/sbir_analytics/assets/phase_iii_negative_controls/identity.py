"""Compatibility shim for the promoted exact award-identity primitive.

Verified (2026-08-05): no frozen artifact in studies/ or specs/ hashes over text
referencing phase_iii_negative_controls.identity as the implementation location,
so this re-export is a strict no-op migration (behavior + text untouched).
"""

from sbir_etl.identity.exact_awards import (
    EXACT_AWARD_IDENTITY_VERSION,
    ExactAwardIdentityProfile,
    IdentityRecoveryError,
    RecoveryStatus,
    reconcile_award_identity_attempts,
    resolve_award_identities,
)


__all__ = [
    "EXACT_AWARD_IDENTITY_VERSION",
    "ExactAwardIdentityProfile",
    "IdentityRecoveryError",
    "RecoveryStatus",
    "reconcile_award_identity_attempts",
    "resolve_award_identities",
]
