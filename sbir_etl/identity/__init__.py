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
    "SUFFIX_TOKENS",
    "SBIR_AWARD_KEY_FIELDS",
    "SBIR_AWARD_KEY_VERSION",
    "CompanyNameMetric",
    "CompanyNameProfile",
    "SbirAwardKeyProfile",
    "company_name_similarity",
    "normalize_company_name",
    "rapidfuzz_jaro_winkler_100",
    "rapidfuzz_ratio_100",
    "rapidfuzz_token_set_100",
    "rapidfuzz_token_sort_100",
    "sbir_award_grain_key",
    "sbir_award_public_id",
    "stable_sbir_award_id",
]
