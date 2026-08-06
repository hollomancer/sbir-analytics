"""Shared company-identity normalization and similarity contracts."""

from .company_names import (
    ENHANCED_ABBREVIATIONS,
    SUFFIX_TOKENS,
    CompanyNameMetric,
    CompanyNameProfile,
    company_name_similarity,
    normalize_company_name,
    rapidfuzz_jaro_winkler_100,
    rapidfuzz_ratio_100,
    rapidfuzz_token_set_100,
    rapidfuzz_token_sort_100,
)
from .exact_awards import (
    EXACT_AWARD_IDENTITY_VERSION,
    ExactAwardIdentityProfile,
    IdentityRecoveryError,
    RecoveryStatus,
    reconcile_award_identity_attempts,
    resolve_award_identities,
)
from .geography import (
    US_JURISDICTION_NAMES_V1,
    US_JURISDICTION_VARIATIONS_V1,
    USJurisdictionProfile,
    VALID_US_JURISDICTION_CODES_V1,
    normalize_us_jurisdiction,
    us_jurisdiction_name,
)
from .sbir_awards import (
    SBIR_AWARD_KEY_FIELDS,
    SBIR_AWARD_KEY_VERSION,
    SbirAwardKeyProfile,
    sbir_award_grain_key,
    sbir_award_public_id,
    stable_sbir_award_id,
)


__all__ = [
    "ENHANCED_ABBREVIATIONS",
    "EXACT_AWARD_IDENTITY_VERSION",
    "SBIR_AWARD_KEY_FIELDS",
    "SBIR_AWARD_KEY_VERSION",
    "SUFFIX_TOKENS",
    "US_JURISDICTION_NAMES_V1",
    "US_JURISDICTION_VARIATIONS_V1",
    "USJurisdictionProfile",
    "VALID_US_JURISDICTION_CODES_V1",
    "CompanyNameMetric",
    "CompanyNameProfile",
    "ExactAwardIdentityProfile",
    "IdentityRecoveryError",
    "RecoveryStatus",
    "SbirAwardKeyProfile",
    "company_name_similarity",
    "normalize_company_name",
    "normalize_us_jurisdiction",
    "rapidfuzz_jaro_winkler_100",
    "rapidfuzz_ratio_100",
    "rapidfuzz_token_set_100",
    "rapidfuzz_token_sort_100",
    "reconcile_award_identity_attempts",
    "resolve_award_identities",
    "sbir_award_grain_key",
    "sbir_award_public_id",
    "stable_sbir_award_id",
    "us_jurisdiction_name",
]
