"""
NAICS enrichment package for SBIR award data.

This package contains modularized NAICS enrichment services for adding NAICS
(North American Industry Classification System) codes to SBIR awards.

Module Structure:
- core: Lightweight NAICS enrichment from USAspending pg_dump files
- fiscal: Comprehensive fiscal-specific NAICS enrichment with hierarchical fallback

Pipeline Usage:
1. Core: Build NAICS index from USAspending data dumps
2. Fiscal: Enrich SBIR awards with hierarchical fallback strategy

Fallback Hierarchy (fiscal):
1. Original SBIR data (confidence: 0.95)
2. USAspending API by UEI/DUNS (confidence: 0.90)
3. USAspending API by CAGE code (confidence: 0.88)
4. USAspending API by contract number/PIID (confidence: 0.87)
5. SAM.gov API (confidence: 0.85)
6. Topic code mapping (confidence: 0.75)
7. Text-based inference (confidence: 0.65)
8. Agency defaults (confidence: 0.50)
9. Sector fallback (confidence: 0.30)

Exported Classes:
- NAICSEnricher: Lightweight USAspending dump processor
- NAICSEnricherConfig: Configuration for core enricher
- FiscalNAICSEnricher: Full-featured fiscal NAICS enricher
- NAICSEnrichmentResult: Result object with confidence tracking

Exported Functions:
- enrich_sbir_awards_with_fiscal_naics: Main fiscal enrichment function
"""

from __future__ import annotations

# Core module (lightweight USAspending dump processing)
from .core import (
    NAICSEnricher,
    NAICSEnricherConfig,
)

# Fiscal module (full-featured fiscal enrichment)
from .fiscal import (
    FiscalNAICSEnricher,
    NAICSEnrichmentResult,
    enrich_sbir_awards_with_fiscal_naics,
)


__all__ = [
    # Core enricher
    "NAICSEnricher",
    "NAICSEnricherConfig",
    # Fiscal enricher
    "FiscalNAICSEnricher",
    "NAICSEnrichmentResult",
    "enrich_sbir_awards_with_fiscal_naics",
]
