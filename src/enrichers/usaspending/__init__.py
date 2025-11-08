"""
USAspending enrichment package for SBIR award data.

This package contains modularized USAspending enrichment services for adding
USAspending.gov data to SBIR awards, including recipient information, NAICS codes,
and transaction data.

Module Structure:
- client: Async API client for USAspending.gov API v2
- enricher: Award enrichment logic with identifier-first matching strategy
- index: Utilities for parsing USAspending pg_dump zip files

Pipeline Usage:
1. Client: Query USAspending API with rate limiting and retry logic
2. Enricher: Match SBIR awards to USAspending recipients
3. Index: Extract table mappings from USAspending dump files

Matching Strategy (enricher):
1. UEI exact match (preferred)
2. DUNS exact match (digits-only)
3. Fuzzy name matching on recipient names

Exported Classes:
- USAspendingAPIClient: Async API client with rate limiting
- USAspendingAPIError: API error (backward compatibility alias)
- USAspendingRateLimitError: Rate limit error (backward compatibility alias)

Exported Functions:
- enrich_sbir_with_usaspending: Main enrichment function
- parse_toc_table_dat_map: Parse table-to-dat file mapping from zip
- extract_table_sample: Extract sample data from dump file
"""

from __future__ import annotations

# Client module
from .client import (
    USAspendingAPIClient,
    USAspendingAPIError,
    USAspendingRateLimitError,
)

# Enricher module
from .enricher import (
    enrich_sbir_with_usaspending,
    normalize_recipient_name,
)

# Index module
from .index import (
    extract_table_sample,
    parse_toc_table_dat_map,
)


__all__ = [
    # Client
    "USAspendingAPIClient",
    "USAspendingAPIError",
    "USAspendingRateLimitError",
    # Enricher
    "enrich_sbir_with_usaspending",
    "normalize_recipient_name",
    # Index
    "parse_toc_table_dat_map",
    "extract_table_sample",
]
