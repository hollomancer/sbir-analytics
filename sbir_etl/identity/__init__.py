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


__all__ = [
    "ENHANCED_ABBREVIATIONS",
    "SUFFIX_TOKENS",
    "CompanyNameMetric",
    "CompanyNameProfile",
    "company_name_similarity",
    "normalize_company_name",
    "rapidfuzz_jaro_winkler_100",
    "rapidfuzz_ratio_100",
    "rapidfuzz_token_set_100",
    "rapidfuzz_token_sort_100",
]
