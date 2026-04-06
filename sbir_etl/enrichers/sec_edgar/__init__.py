"""
SEC EDGAR enrichment package for SBIR company analysis.

This package provides an async client for SEC EDGAR APIs to enrich SBIR
companies with public filing data, financial metrics, and M&A event detection.

Module Structure:
- client: Async API client for SEC EDGAR EFTS and companyfacts APIs
- enricher: Company-level enrichment logic (CIK resolution, financials, 8-K events)

Exported Classes:
- EdgarAPIClient: Async API client with rate limiting (10 req/s per SEC fair-access policy)
- enrich_companies_with_edgar: Main enrichment function for SBIR company DataFrames
"""

from __future__ import annotations

from .client import EdgarAPIClient
from .enricher import enrich_companies_with_edgar

__all__ = [
    "EdgarAPIClient",
    "enrich_companies_with_edgar",
]
