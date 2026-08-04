"""Compatibility imports for the promoted exact award-identity primitive."""

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
