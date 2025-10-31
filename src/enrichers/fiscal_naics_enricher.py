"""
NAICS enrichment service for fiscal returns analysis.

This module extends existing enrichment patterns with fiscal-specific NAICS requirements,
implementing a hierarchical fallback chain to maximize NAICS coverage for economic modeling.

Fallback chain:
1. Original SBIR data (confidence: 0.95)
2. USAspending API by UEI/DUNS (confidence: 0.90)
3. USAspending API by CAGE code (confidence: 0.88)
4. USAspending API by contract number/PIID (confidence: 0.87)
5. SAM.gov API (confidence: 0.85)
6. Topic code mapping (confidence: 0.75)
7. Text-based inference from abstract/title (confidence: 0.65)
8. Agency defaults (confidence: 0.50)
9. Sector fallback (confidence: 0.30)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd
from loguru import logger

from ..config.loader import get_config


@dataclass
class NAICSEnrichmentResult:
    """Result of NAICS enrichment with confidence and source tracking."""

    naics_code: str | None
    confidence: float
    source: str
    method: str
    timestamp: datetime
    metadata: dict[str, Any]


class FiscalNAICSEnricher:
    """NAICS enrichment service for fiscal returns analysis."""

    def __init__(self, config: dict[str, Any] | None = None):
        """Initialize the NAICS enricher.
        
        Args:
            config: Optional configuration override
        """
        self.config = config or get_config().fiscal_analysis
        self.quality_thresholds = self.config.quality_thresholds

        # Agency default NAICS mappings
        self.agency_defaults = {
            "DOD": "3364",  # Aerospace product and parts manufacturing
            "ARMY": "3364",
            "NAVY": "3364",
            "AIR FORCE": "3364",
            "HHS": "5417",  # Scientific research and development services
            "NIH": "5417",
            "CDC": "5417",
            "DOE": "5417",  # Energy research and development
            "NASA": "5417", # Space research and development
            "NSF": "5417",  # Scientific research
            "EPA": "5417",  # Environmental research
            "USDA": "5417", # Agricultural research
            "DHS": "5415",  # Computer systems design services
            "DOT": "5415",  # Transportation research
            "DOC": "5415",  # Commerce and technology research
            "NIST": "5415", # Standards and technology research
        }

        # Sector fallback code for unclassified awards
        self.sector_fallback_code = "5415"  # Computer systems design and related services

        # Topic code to NAICS mappings (agency-specific)
        # These are based on common patterns in SBIR topic codes
        self.topic_code_naics_mappings = {
            # DoD/Air Force topics (common patterns)
            "AF": "3364",  # Aerospace
            "ARMY": "3364",  # Defense manufacturing
            "NAVY": "3364",  # Naval systems
            "DOD": "3364",
            # Health/Medical topics
            "NIH": "5417",  # Biomedical research
            "HHS": "5417",
            # Energy topics
            "DOE": "5417",  # Energy R&D
            # Technology/Software topics
            "ST": "5415",  # Software/tech (common prefix)
            "IT": "5415",  # Information technology
            "AI": "5415",  # Artificial intelligence
            "ML": "5415",  # Machine learning
        }

        # Keyword patterns for text-based NAICS inference
        # Maps keywords/phrases to likely NAICS codes
        self.naics_keyword_patterns = {
            "5417": [  # Scientific R&D services
                "research", "development", "biomedical", "biotech", "pharmaceutical",
                "clinical trial", "drug", "therapeutic", "vaccine", "diagnostic",
                "genetic", "molecular", "protein", "enzyme", "antibody",
            ],
            "5415": [  # Computer systems design
                "software", "algorithm", "artificial intelligence", "machine learning",
                "data", "analytics", "cyber", "network", "database", "cloud",
                "computing", "system", "platform", "application", "digital",
            ],
            "3364": [  # Aerospace manufacturing
                "aerospace", "aircraft", "missile", "rocket", "propulsion", "engine",
                "satellite", "space", "defense", "military", "drone", "uav",
            ],
            "5416": [  # Management consulting
                "consulting", "management", "strategic", "planning", "analysis",
            ],
            "5413": [  # Architectural/engineering services
                "engineering", "design", "architectural", "technical",
            ],
        }

        logger.info(f"Initialized FiscalNAICSEnricher with {len(self.agency_defaults)} agency mappings")

    def validate_naics_code(self, naics_code: str) -> bool:
        """Validate NAICS code format and structure.
        
        Args:
            naics_code: NAICS code to validate
            
        Returns:
            True if valid NAICS code format
        """
        if not naics_code:
            return False

        # Remove any non-digit characters
        clean_code = re.sub(r'\D', '', str(naics_code))

        # NAICS codes should be 2-6 digits
        if len(clean_code) < 2 or len(clean_code) > 6:
            return False

        # Check if it's a valid numeric string
        try:
            int(clean_code)
            return True
        except ValueError:
            return False

    def normalize_naics_code(self, naics_code: str) -> str | None:
        """Normalize NAICS code to standard format.
        
        Args:
            naics_code: Raw NAICS code
            
        Returns:
            Normalized NAICS code or None if invalid
        """
        if not naics_code:
            return None

        # Remove non-digit characters and leading zeros
        clean_code = re.sub(r'\D', '', str(naics_code)).lstrip('0')

        if not clean_code:
            return None

        # Validate the cleaned code
        if self.validate_naics_code(clean_code):
            return clean_code

        return None

    def enrich_from_original_data(self, award_row: pd.Series) -> NAICSEnrichmentResult | None:
        """Extract NAICS from original SBIR data.
        
        Args:
            award_row: SBIR award row
            
        Returns:
            NAICS enrichment result or None
        """
        # Check common NAICS column names
        naics_columns = ['NAICS', 'naics', 'NAICS_Code', 'naics_code', 'Primary_NAICS']

        for col in naics_columns:
            if col in award_row.index and pd.notna(award_row[col]):
                naics_code = self.normalize_naics_code(str(award_row[col]))
                if naics_code:
                    return NAICSEnrichmentResult(
                        naics_code=naics_code,
                        confidence=0.95,
                        source="original_data",
                        method="direct_field",
                        timestamp=datetime.now(),
                        metadata={"original_column": col, "original_value": str(award_row[col])}
                    )

        return None

    def enrich_from_usaspending(self, award_row: pd.Series, usaspending_df: pd.DataFrame) -> NAICSEnrichmentResult | None:
        """Enrich NAICS from USAspending data.
        
        Args:
            award_row: SBIR award row
            usaspending_df: USAspending data
            
        Returns:
            NAICS enrichment result or None
        """
        # Look for existing USAspending match
        if '_usaspending_match_method' in award_row.index and pd.notna(award_row['_usaspending_match_method']):
            # Use existing match
            if 'recipient_naics' in award_row.index and pd.notna(award_row['recipient_naics']):
                naics_code = self.normalize_naics_code(str(award_row['recipient_naics']))
                if naics_code:
                    confidence = 0.90 if 'exact' in str(award_row['_usaspending_match_method']) else 0.85
                    return NAICSEnrichmentResult(
                        naics_code=naics_code,
                        confidence=confidence,
                        source="usaspending_existing",
                        method=str(award_row['_usaspending_match_method']),
                        timestamp=datetime.now(),
                        metadata={"match_method": str(award_row['_usaspending_match_method'])}
                    )

        # Attempt new USAspending lookup by UEI/DUNS
        uei = award_row.get('UEI') or award_row.get('uei')
        duns = award_row.get('Duns') or award_row.get('duns')

        if uei and pd.notna(uei):
            matches = usaspending_df[usaspending_df['recipient_uei'] == str(uei)]
            if not matches.empty and 'naics_code' in matches.columns:
                naics_codes = matches['naics_code'].dropna()
                if not naics_codes.empty:
                    # Use most common NAICS code for this recipient
                    most_common_naics = naics_codes.mode().iloc[0] if not naics_codes.mode().empty else naics_codes.iloc[0]
                    naics_code = self.normalize_naics_code(str(most_common_naics))
                    if naics_code:
                        return NAICSEnrichmentResult(
                            naics_code=naics_code,
                            confidence=0.90,
                            source="usaspending_uei",
                            method="uei_lookup",
                            timestamp=datetime.now(),
                            metadata={"uei": str(uei), "matches_found": len(matches)}
                        )

        if duns and pd.notna(duns):
            # Clean DUNS to digits only
            clean_duns = re.sub(r'\D', '', str(duns))
            if clean_duns:
                matches = usaspending_df[usaspending_df['recipient_duns'] == clean_duns]
                if not matches.empty and 'naics_code' in matches.columns:
                    naics_codes = matches['naics_code'].dropna()
                    if not naics_codes.empty:
                        most_common_naics = naics_codes.mode().iloc[0] if not naics_codes.mode().empty else naics_codes.iloc[0]
                        naics_code = self.normalize_naics_code(str(most_common_naics))
                        if naics_code:
                            return NAICSEnrichmentResult(
                                naics_code=naics_code,
                                confidence=0.85,
                                source="usaspending_duns",
                                method="duns_lookup",
                                timestamp=datetime.now(),
                                metadata={"duns": clean_duns, "matches_found": len(matches)}
                            )

        return None

    def enrich_from_usaspending_cage(self, award_row: pd.Series, usaspending_df: pd.DataFrame) -> NAICSEnrichmentResult | None:
        """Enrich NAICS from USAspending data using CAGE code lookup.
        
        Args:
            award_row: SBIR award row
            usaspending_df: USAspending data
            
        Returns:
            NAICS enrichment result or None
        """
        # Look for CAGE code in award data
        cage_code = (
            award_row.get('CAGE') or 
            award_row.get('cage') or 
            award_row.get('Cage') or
            award_row.get('company_cage') or
            award_row.get('recipient_cage')
        )
        
        if not cage_code or pd.isna(cage_code):
            return None
        
        # Normalize CAGE code (5 characters, uppercase)
        clean_cage = str(cage_code).strip().upper()
        if len(clean_cage) != 5:
            return None
        
        # Look for CAGE code matches in USAspending data
        # Check common column names for CAGE code
        cage_columns = ['cage_code', 'recipient_cage', 'contractor_cage', 'vendor_cage']
        
        for col in cage_columns:
            if col in usaspending_df.columns:
                matches = usaspending_df[usaspending_df[col].astype(str).str.upper().str.strip() == clean_cage]
                if not matches.empty and 'naics_code' in matches.columns:
                    naics_codes = matches['naics_code'].dropna()
                    if not naics_codes.empty:
                        # Use most common NAICS code for this CAGE code
                        most_common_naics = naics_codes.mode().iloc[0] if not naics_codes.mode().empty else naics_codes.iloc[0]
                        naics_code = self.normalize_naics_code(str(most_common_naics))
                        if naics_code:
                            return NAICSEnrichmentResult(
                                naics_code=naics_code,
                                confidence=0.88,
                                source="usaspending_cage",
                                method="cage_lookup",
                                timestamp=datetime.now(),
                                metadata={"cage_code": clean_cage, "matches_found": len(matches)}
                            )
        
        return None

    def enrich_from_usaspending_contract(self, award_row: pd.Series, usaspending_df: pd.DataFrame) -> NAICSEnrichmentResult | None:
        """Enrich NAICS from USAspending data using contract number/PIID lookup.
        
        Args:
            award_row: SBIR award row
            usaspending_df: USAspending data
            
        Returns:
            NAICS enrichment result or None
        """
        # Look for contract number in award data
        contract_number = (
            award_row.get('Contract') or
            award_row.get('contract') or
            award_row.get('contract_number') or
            award_row.get('piid')
        )
        
        if not contract_number or pd.isna(contract_number):
            return None
        
        contract_str = str(contract_number).strip()
        
        # Look for contract matches in USAspending data
        # Check common column names for contract/PIID
        contract_columns = ['piid', 'contract_number', 'contract_id', 'award_id']
        
        for col in contract_columns:
            if col in usaspending_df.columns:
                matches = usaspending_df[usaspending_df[col].astype(str).str.strip() == contract_str]
                if not matches.empty and 'naics_code' in matches.columns:
                    naics_codes = matches['naics_code'].dropna()
                    if not naics_codes.empty:
                        # Use most common NAICS code for this contract
                        most_common_naics = naics_codes.mode().iloc[0] if not naics_codes.mode().empty else naics_codes.iloc[0]
                        naics_code = self.normalize_naics_code(str(most_common_naics))
                        if naics_code:
                            return NAICSEnrichmentResult(
                                naics_code=naics_code,
                                confidence=0.87,
                                source="usaspending_contract",
                                method="contract_lookup",
                                timestamp=datetime.now(),
                                metadata={"contract_number": contract_str, "matches_found": len(matches)}
                            )
        
        return None

    def enrich_from_topic_code(self, award_row: pd.Series) -> NAICSEnrichmentResult | None:
        """Enrich NAICS from topic code mapping.
        
        Args:
            award_row: SBIR award row
            
        Returns:
            NAICS enrichment result or None
        """
        # Look for topic code
        topic_code = (
            award_row.get('Topic Code') or
            award_row.get('topic_code') or
            award_row.get('Topic_Code') or
            award_row.get('topic')
        )
        
        if not topic_code or pd.isna(topic_code):
            return None
        
        topic_str = str(topic_code).strip().upper()
        
        # Try direct mapping first
        if topic_str in self.topic_code_naics_mappings:
            naics_code = self.topic_code_naics_mappings[topic_str]
            return NAICSEnrichmentResult(
                naics_code=naics_code,
                confidence=0.75,
                source="topic_code_mapping",
                method="direct_topic_match",
                timestamp=datetime.now(),
                metadata={"topic_code": topic_str}
            )
        
        # Try partial matches (e.g., "AF20-028" -> "AF")
        for prefix, naics_code in self.topic_code_naics_mappings.items():
            if topic_str.startswith(prefix):
                return NAICSEnrichmentResult(
                    naics_code=naics_code,
                    confidence=0.70,
                    source="topic_code_mapping",
                    method="prefix_topic_match",
                    timestamp=datetime.now(),
                    metadata={"topic_code": topic_str, "matched_prefix": prefix}
                )
        
        return None

    def enrich_from_text_inference(self, award_row: pd.Series) -> NAICSEnrichmentResult | None:
        """Enrich NAICS from text analysis of abstract and title.
        
        Args:
            award_row: SBIR award row
            
        Returns:
            NAICS enrichment result or None
        """
        # Collect text fields
        text_fields = []
        for field in ['Abstract', 'abstract', 'Award Title', 'award_title', 'Topic', 'topic']:
            if field in award_row.index and pd.notna(award_row[field]):
                text_fields.append(str(award_row[field]).lower())
        
        if not text_fields:
            return None
        
        combined_text = ' '.join(text_fields)
        
        # Score each NAICS code based on keyword matches
        naics_scores: dict[str, dict[str, Any]] = {}
        
        for naics_code, keywords in self.naics_keyword_patterns.items():
            score = 0.0
            matches = []
            
            for keyword in keywords:
                if keyword.lower() in combined_text:
                    score += 1.0
                    matches.append(keyword)
            
            if score > 0:
                # Normalize score by number of keywords for that NAICS
                normalized_score = score / len(keywords)
                naics_scores[naics_code] = {
                    'score': normalized_score,
                    'matches': matches,
                    'match_count': len(matches)
                }
        
        if not naics_scores:
            return None
        
        # Find NAICS code with highest score
        best_naics = max(naics_scores.items(), key=lambda x: (x[1]['score'], x[1]['match_count']))
        naics_code = best_naics[0]
        score_data = best_naics[1]
        
        # Confidence based on match strength (more matches = higher confidence)
        # Base confidence 0.60, increases with more matches up to 0.75
        base_confidence = 0.60
        match_bonus = min(0.15, score_data['match_count'] * 0.05)
        confidence = base_confidence + match_bonus
        
        return NAICSEnrichmentResult(
            naics_code=naics_code,
            confidence=confidence,
            source="text_inference",
            method="keyword_analysis",
            timestamp=datetime.now(),
            metadata={
                "matched_keywords": score_data['matches'],
                "match_count": score_data['match_count'],
                "score": score_data['score']
            }
        )

    def enrich_from_sam_gov(self, award_row: pd.Series) -> NAICSEnrichmentResult | None:
        """Enrich NAICS from SAM.gov API (placeholder for future implementation).
        
        Args:
            award_row: SBIR award row
            
        Returns:
            NAICS enrichment result or None
        """
        # Placeholder for SAM.gov API integration
        # This would require API key and rate limiting implementation
        logger.debug("SAM.gov NAICS enrichment not yet implemented")
        return None

    def enrich_from_agency_defaults(self, award_row: pd.Series) -> NAICSEnrichmentResult | None:
        """Apply agency-specific default NAICS codes.
        
        Args:
            award_row: SBIR award row
            
        Returns:
            NAICS enrichment result or None
        """
        # Check agency column
        agency_columns = ['Agency', 'agency', 'Awarding_Agency', 'awarding_agency']

        for col in agency_columns:
            if col in award_row.index and pd.notna(award_row[col]):
                agency = str(award_row[col]).upper().strip()

                # Direct match
                if agency in self.agency_defaults:
                    return NAICSEnrichmentResult(
                        naics_code=self.agency_defaults[agency],
                        confidence=0.50,
                        source="agency_default",
                        method="direct_mapping",
                        timestamp=datetime.now(),
                        metadata={"agency": agency, "column": col}
                    )

                # Partial match for complex agency names
                for agency_key, naics_code in self.agency_defaults.items():
                    if agency_key in agency or agency in agency_key:
                        return NAICSEnrichmentResult(
                            naics_code=naics_code,
                            confidence=0.45,
                            source="agency_default",
                            method="partial_mapping",
                            timestamp=datetime.now(),
                            metadata={"agency": agency, "matched_key": agency_key, "column": col}
                        )

        return None

    def enrich_from_sector_fallback(self, award_row: pd.Series) -> NAICSEnrichmentResult:
        """Apply sector fallback NAICS code.
        
        Args:
            award_row: SBIR award row
            
        Returns:
            NAICS enrichment result with fallback code
        """
        return NAICSEnrichmentResult(
            naics_code=self.sector_fallback_code,
            confidence=0.30,
            source="sector_fallback",
            method="default_assignment",
            timestamp=datetime.now(),
            metadata={"fallback_code": self.sector_fallback_code}
        )

    def enrich_single_award(self, award_row: pd.Series, usaspending_df: pd.DataFrame | None = None) -> NAICSEnrichmentResult:
        """Enrich a single award with NAICS code using hierarchical fallback.
        
        Args:
            award_row: SBIR award row
            usaspending_df: Optional USAspending data for enrichment
            
        Returns:
            NAICS enrichment result
        """
        # Try each enrichment source in order of preference
        enrichment_methods = [
            self.enrich_from_original_data,
            lambda row: self.enrich_from_usaspending(row, usaspending_df) if usaspending_df is not None else None,
            lambda row: self.enrich_from_usaspending_cage(row, usaspending_df) if usaspending_df is not None else None,
            lambda row: self.enrich_from_usaspending_contract(row, usaspending_df) if usaspending_df is not None else None,
            self.enrich_from_sam_gov,
            self.enrich_from_topic_code,
            self.enrich_from_text_inference,
            self.enrich_from_agency_defaults,
        ]

        for method in enrichment_methods:
            try:
                result = method(award_row)
                if result and result.naics_code:
                    return result
            except Exception as e:
                logger.warning(f"NAICS enrichment method failed: {e}")
                continue

        # Final fallback
        return self.enrich_from_sector_fallback(award_row)

    def enrich_awards_dataframe(self, awards_df: pd.DataFrame, usaspending_df: pd.DataFrame | None = None) -> pd.DataFrame:
        """Enrich entire awards DataFrame with NAICS codes.
        
        Args:
            awards_df: SBIR awards DataFrame
            usaspending_df: Optional USAspending data for enrichment
            
        Returns:
            Enriched DataFrame with NAICS columns
        """
        enriched_df = awards_df.copy()

        # Initialize enrichment columns
        enriched_df['fiscal_naics_code'] = None
        enriched_df['fiscal_naics_confidence'] = None
        enriched_df['fiscal_naics_source'] = None
        enriched_df['fiscal_naics_method'] = None
        enriched_df['fiscal_naics_timestamp'] = None
        enriched_df['fiscal_naics_metadata'] = None

        logger.info(f"Starting NAICS enrichment for {len(awards_df)} awards")

        # Track enrichment statistics
        source_counts = {}
        confidence_distribution = []

        # Enrich each award
        for idx, row in awards_df.iterrows():
            try:
                result = self.enrich_single_award(row, usaspending_df)

                # Store enrichment results
                enriched_df.at[idx, 'fiscal_naics_code'] = result.naics_code
                enriched_df.at[idx, 'fiscal_naics_confidence'] = result.confidence
                enriched_df.at[idx, 'fiscal_naics_source'] = result.source
                enriched_df.at[idx, 'fiscal_naics_method'] = result.method
                enriched_df.at[idx, 'fiscal_naics_timestamp'] = result.timestamp
                enriched_df.at[idx, 'fiscal_naics_metadata'] = str(result.metadata)

                # Track statistics
                source_counts[result.source] = source_counts.get(result.source, 0) + 1
                confidence_distribution.append(result.confidence)

            except Exception as e:
                logger.error(f"Failed to enrich award {idx}: {e}")
                # Apply fallback for failed enrichments
                fallback_result = self.enrich_from_sector_fallback(row)
                enriched_df.at[idx, 'fiscal_naics_code'] = fallback_result.naics_code
                enriched_df.at[idx, 'fiscal_naics_confidence'] = fallback_result.confidence
                enriched_df.at[idx, 'fiscal_naics_source'] = fallback_result.source
                enriched_df.at[idx, 'fiscal_naics_method'] = fallback_result.method
                enriched_df.at[idx, 'fiscal_naics_timestamp'] = fallback_result.timestamp
                enriched_df.at[idx, 'fiscal_naics_metadata'] = str(fallback_result.metadata)

        # Log enrichment statistics
        total_awards = len(awards_df)
        naics_coverage = enriched_df['fiscal_naics_code'].notna().sum() / total_awards
        avg_confidence = sum(confidence_distribution) / len(confidence_distribution) if confidence_distribution else 0

        logger.info("NAICS enrichment complete:")
        logger.info(f"  Coverage: {naics_coverage:.1%} ({enriched_df['fiscal_naics_code'].notna().sum()}/{total_awards})")
        logger.info(f"  Average confidence: {avg_confidence:.2f}")
        logger.info(f"  Source breakdown: {source_counts}")

        return enriched_df

    def validate_enrichment_quality(self, enriched_df: pd.DataFrame) -> dict[str, Any]:
        """Validate enrichment quality against configured thresholds.
        
        Args:
            enriched_df: Enriched DataFrame
            
        Returns:
            Quality validation results
        """
        total_awards = len(enriched_df)
        naics_coverage = enriched_df['fiscal_naics_code'].notna().sum() / total_awards if total_awards > 0 else 0

        # Calculate confidence distribution
        confidences = enriched_df['fiscal_naics_confidence'].dropna()
        high_confidence_count = (confidences >= 0.80).sum() if not confidences.empty else 0
        medium_confidence_count = ((confidences >= 0.60) & (confidences < 0.80)).sum() if not confidences.empty else 0
        low_confidence_count = (confidences < 0.60).sum() if not confidences.empty else 0

        # Source distribution
        source_counts = enriched_df['fiscal_naics_source'].value_counts().to_dict()

        # Quality assessment
        quality_results = {
            "total_awards": total_awards,
            "naics_coverage_rate": naics_coverage,
            "naics_coverage_threshold": self.quality_thresholds.get("naics_coverage_rate", 0.85),
            "coverage_meets_threshold": naics_coverage >= self.quality_thresholds.get("naics_coverage_rate", 0.85),
            "confidence_distribution": {
                "high_confidence": int(high_confidence_count),
                "medium_confidence": int(medium_confidence_count),
                "low_confidence": int(low_confidence_count),
            },
            "source_distribution": source_counts,
            "average_confidence": float(confidences.mean()) if not confidences.empty else 0.0,
            "fallback_usage_rate": source_counts.get("sector_fallback", 0) / total_awards if total_awards > 0 else 0,
        }

        # Log quality assessment
        if quality_results["coverage_meets_threshold"]:
            logger.info(f"NAICS enrichment quality: PASS (coverage: {naics_coverage:.1%})")
        else:
            logger.warning(f"NAICS enrichment quality: FAIL (coverage: {naics_coverage:.1%}, threshold: {quality_results['naics_coverage_threshold']:.1%})")

        return quality_results


def enrich_sbir_awards_with_fiscal_naics(
    awards_df: pd.DataFrame,
    usaspending_df: pd.DataFrame | None = None,
    config: dict[str, Any] | None = None
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Main function to enrich SBIR awards with fiscal NAICS codes.
    
    Args:
        awards_df: SBIR awards DataFrame
        usaspending_df: Optional USAspending data for enrichment
        config: Optional configuration override
        
    Returns:
        Tuple of (enriched DataFrame, quality metrics)
    """
    enricher = FiscalNAICSEnricher(config)
    enriched_df = enricher.enrich_awards_dataframe(awards_df, usaspending_df)
    quality_metrics = enricher.validate_enrichment_quality(enriched_df)

    return enriched_df, quality_metrics
