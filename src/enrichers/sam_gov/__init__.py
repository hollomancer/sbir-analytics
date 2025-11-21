"""
SAM.gov enrichment package for SBIR award data.

This package contains modularized SAM.gov enrichment services for adding
SAM.gov entity information to SBIR awards, including UEI, CAGE codes,
company names, addresses, and NAICS codes.

Module Structure:
- client: Async API client for SAM.gov Entity Information API v3

Pipeline Usage:
1. Client: Query SAM.gov API with rate limiting and retry logic
2. Bulk data: Use parquet file for bulk entity lookups (preferred)

Exported Classes:
- SAMGovAPIClient: Async API client with rate limiting
- SAMGovAPIError: API error (backward compatibility alias)
- SAMGovRateLimitError: Rate limit error (backward compatibility alias)
"""

from __future__ import annotations

# Client module
from .client import SAMGovAPIClient, SAMGovAPIError, SAMGovRateLimitError


__all__ = [
    # Client
    "SAMGovAPIClient",
    "SAMGovAPIError",
    "SAMGovRateLimitError",
]
