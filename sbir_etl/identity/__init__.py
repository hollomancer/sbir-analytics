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
from .geography import (
    US_JURISDICTION_NAMES_V1,
    US_JURISDICTION_VARIATIONS_V1,
    USJurisdictionProfile,
    VALID_US_JURISDICTION_CODES_V1,
    normalize_us_jurisdiction,
    us_jurisdiction_name,
)


__all__ = [
    "ENHANCED_ABBREVIATIONS",
    "SUFFIX_TOKENS",
    "US_JURISDICTION_NAMES_V1",
    "US_JURISDICTION_VARIATIONS_V1",
    "USJurisdictionProfile",
    "VALID_US_JURISDICTION_CODES_V1",
    "CompanyNameMetric",
    "CompanyNameProfile",
    "company_name_similarity",
    "normalize_company_name",
    "normalize_us_jurisdiction",
    "rapidfuzz_jaro_winkler_100",
    "rapidfuzz_ratio_100",
    "rapidfuzz_token_set_100",
    "rapidfuzz_token_sort_100",
    "us_jurisdiction_name",
]
