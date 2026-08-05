"""Compatibility imports for the promoted exact award-identity primitive.

The implementation now lives in ``sbir_etl.identity.exact_awards``. This
module is a pure re-export shim so that existing callers within
``phase_iii_negative_controls`` keep working without change.

Frozen-spec note: no frozen artifact in ``studies/`` or ``specs/`` hashes
over text that references this module path as the canonical implementation
location. The relocation is behaviorally transparent; no amendment is
required.
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
