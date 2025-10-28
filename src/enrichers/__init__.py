"""Data enrichment modules for external API integration.

This package exposes enrichment modules and search provider adapters.
Import the `search_providers` subpackage to access provider implementations
and the `BaseSearchProvider` abstraction.
"""

# Re-export commonly used enrichment utilities
from .chunked_enrichment import (
    ChunkedEnricher,
    create_dynamic_outputs_enrichment,
    combine_enriched_chunks,
)
from .company_enricher import enrich_awards_with_companies
from .usaspending_enricher import enrich_sbir_with_usaspending

# Re-export search provider package and base types for convenience
from . import search_providers as search_providers
from .search_providers.base import BaseSearchProvider, ProviderResponse, ProviderResult

__all__ = [
    "ChunkedEnricher",
    "create_dynamic_outputs_enrichment",
    "combine_enriched_chunks",
    "enrich_awards_with_companies",
    "enrich_sbir_with_usaspending",
    "search_providers",
    "BaseSearchProvider",
    "ProviderResponse",
    "ProviderResult",
]
