# packages/sbir-ml/sbir_ml/transition/features/vendor_crosswalk.py
"""
Vendor name similarity scorer for transition vendor matching.

`vendor_resolver.VendorResolver` uses `_fuzzy_score` for fuzzy name matches.
"""

from __future__ import annotations

from sbir_etl.identity import CompanyNameMetric, company_name_similarity


def _fuzzy_score(a: str, b: str) -> float:
    return company_name_similarity(a, b, metric=CompanyNameMetric.TOKEN_SORT)
