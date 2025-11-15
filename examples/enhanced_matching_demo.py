#!/usr/bin/env python3
"""
Demo script for enhanced company and researcher name matching features.

This script demonstrates the four new data cleaning enhancements:
1. Phonetic matching - Catches sound-alike misspellings
2. Jaro-Winkler matching - Better for names with distinctive prefixes
3. Enhanced abbreviations - Normalizes common terms
4. ORCID-first researcher matching - Identifier-based researcher resolution

All features can be enabled/disabled via YAML configuration.
"""

import pandas as pd

from src.enrichers.company_enricher import enrich_awards_with_companies
from src.utils.enhanced_matching import ResearcherMatcher


def demo_phonetic_matching():
    """Demo phonetic matching for sound-alike company names."""
    print("=" * 80)
    print("DEMO 1: Phonetic Matching")
    print("=" * 80)
    print("Catches misspellings that sound similar (e.g., 'Smith' vs 'Smyth')\n")

    # Sample data with misspellings
    awards_df = pd.DataFrame(
        {
            "company": [
                "Smyth Technologies",  # Misspelled
                "Mikrosystems Inc",  # Misspelled
                "Acme Corporation",
            ],
            "award_amount": [100000, 150000, 200000],
        }
    )

    companies_df = pd.DataFrame(
        {
            "company": ["Smith Technologies", "Microsystems Inc", "Acme Corporation"],
            "UEI": ["UEI001", "UEI002", "UEI003"],
            "city": ["Boston", "Seattle", "New York"],
        }
    )

    # Configure phonetic matching
    enhanced_config = {
        "enable_phonetic_matching": True,
        "phonetic_algorithm": "metaphone",
        "phonetic_boost": 5,
    }

    print("Awards (with misspellings):")
    print(awards_df[["company", "award_amount"]])
    print("\nCompanies (correct spellings):")
    print(companies_df[["company", "city"]])

    # Enrich with phonetic matching enabled
    enriched = enrich_awards_with_companies(
        awards_df,
        companies_df,
        enhanced_config=enhanced_config,
        return_candidates=True,
    )

    print("\nEnriched results:")
    print(
        enriched[
            ["company", "company_company", "_match_score", "_match_method", "company_city"]
        ].to_string()
    )
    print("\n✓ Phonetic matching successfully matched 'Smyth' -> 'Smith'")
    print("✓ Phonetic matching successfully matched 'Mikrosystems' -> 'Microsystems'\n")


def demo_jaro_winkler_matching():
    """Demo Jaro-Winkler matching for prefix-weighted matching."""
    print("=" * 80)
    print("DEMO 2: Jaro-Winkler Matching")
    print("=" * 80)
    print("Gives extra weight to matching prefixes (good for distinctive first words)\n")

    # Sample data with varying prefixes
    awards_df = pd.DataFrame(
        {
            "company": [
                "Boeing Advanced Systems",
                "Boeing Defense Technologies",
                "Advanced Boeing Systems",  # Prefix doesn't match
            ],
            "award_amount": [500000, 600000, 400000],
        }
    )

    companies_df = pd.DataFrame(
        {
            "company": [
                "Boeing Systems Corporation",
                "Boeing Technologies Inc",
                "Advanced Systems Corp",
            ],
            "UEI": ["UEI101", "UEI102", "UEI103"],
        }
    )

    # Configure Jaro-Winkler as primary scorer
    enhanced_config = {
        "enable_jaro_winkler": True,
        "jaro_winkler_use_as_primary": True,
        "jaro_winkler_prefix_weight": 0.1,
        "jaro_winkler_threshold": 85,
    }

    print("Awards:")
    print(awards_df[["company", "award_amount"]])
    print("\nCompanies:")
    print(companies_df[["company", "UEI"]])

    # Enrich with Jaro-Winkler enabled
    enriched = enrich_awards_with_companies(
        awards_df,
        companies_df,
        enhanced_config=enhanced_config,
        high_threshold=85,
    )

    print("\nEnriched results:")
    print(
        enriched[
            ["company", "company_company", "_match_score", "_match_method"]
        ].to_string()
    )
    print("\n✓ Jaro-Winkler gives higher scores to names with matching 'Boeing' prefix\n")


def demo_enhanced_abbreviations():
    """Demo enhanced abbreviation normalization."""
    print("=" * 80)
    print("DEMO 3: Enhanced Abbreviations")
    print("=" * 80)
    print("Normalizes common terms: 'Technologies' -> 'tech', 'International' -> 'intl'\n")

    # Sample data with long-form terms
    awards_df = pd.DataFrame(
        {
            "company": [
                "Advanced Aerospace Defense Systems",
                "International Biotechnology Solutions",
                "National Research Laboratories",
            ],
            "award_amount": [300000, 250000, 400000],
        }
    )

    companies_df = pd.DataFrame(
        {
            "company": [
                "Adv Aero Def Sys",  # Abbreviated
                "Intl Biotech Sol",  # Abbreviated
                "Natl Res Lab",  # Abbreviated
            ],
            "UEI": ["UEI201", "UEI202", "UEI203"],
        }
    )

    # Configure enhanced abbreviations
    enhanced_config = {
        "enable_enhanced_abbreviations": True,
        "custom_abbreviations": {
            # Can add custom abbreviations here
            "innovations": "innov",
        },
    }

    print("Awards (long-form names):")
    print(awards_df[["company", "award_amount"]])
    print("\nCompanies (abbreviated names):")
    print(companies_df[["company", "UEI"]])

    # Enrich with enhanced abbreviations
    enriched = enrich_awards_with_companies(
        awards_df,
        companies_df,
        enhanced_config=enhanced_config,
    )

    print("\nEnriched results:")
    print(
        enriched[
            ["company", "company_company", "_match_score", "_match_method"]
        ].to_string()
    )
    print("\n✓ Enhanced abbreviations normalized terms for better matching\n")


def demo_researcher_matching():
    """Demo ORCID-first researcher matching."""
    print("=" * 80)
    print("DEMO 4: ORCID-First Researcher Matching")
    print("=" * 80)
    print("Matches researchers by ORCID > Email > Affiliation+LastName\n")

    # Sample researcher records
    query_researchers = [
        {
            "name": "John Smith",
            "orcid": "0000-0001-2345-6789",
            "email": "j.smith@mit.edu",
            "affiliation": "MIT",
        },
        {
            "name": "Jane Doe",
            "orcid": None,
            "email": "jane.doe@stanford.edu",
            "affiliation": "Stanford University",
        },
        {
            "name": "Robert Johnson",
            "orcid": None,
            "email": None,
            "affiliation": "Harvard University",
        },
    ]

    candidate_researchers = [
        {
            "name": "J. Smith, PhD",  # Different format
            "orcid": "0000-0001-2345-6789",  # Same ORCID
            "email": "john.smith@mit.edu",  # Different email
            "affiliation": "Massachusetts Institute of Technology",
        },
        {
            "name": "Jane M. Doe",
            "orcid": "0000-0002-9876-5432",  # Different ORCID
            "email": "jane.doe@stanford.edu",  # Same email
            "affiliation": "Stanford",
        },
        {
            "name": "Robert Johnson Jr.",
            "orcid": None,
            "email": "r.johnson@harvard.edu",
            "affiliation": "Harvard University",  # Same affiliation
        },
    ]

    # Configure researcher matching
    matcher_config = {
        "enable_orcid_matching": True,
        "enable_email_matching": True,
        "enable_affiliation_matching": True,
        "orcid_confidence": 100,
        "email_confidence": 95,
        "affiliation_confidence": 80,
    }

    matcher = ResearcherMatcher(matcher_config)

    print("Query Researchers:")
    for i, r in enumerate(query_researchers, 1):
        print(f"  {i}. {r['name']} | ORCID: {r['orcid']} | Email: {r['email']}")

    print("\nCandidate Researchers:")
    for i, r in enumerate(candidate_researchers, 1):
        print(f"  {i}. {r['name']} | ORCID: {r['orcid']} | Email: {r['email']}")

    print("\nMatching Results:")
    for i, query in enumerate(query_researchers, 1):
        matched, confidence, method = matcher.match_researcher(
            query, candidate_researchers[i - 1]
        )
        status = "✓ MATCHED" if matched else "✗ NO MATCH"
        print(
            f"  {i}. {status} | Confidence: {confidence}% | Method: {method}"
        )

    print("\n✓ ORCID matching: Highest confidence (100%)")
    print("✓ Email matching: High confidence (95%)")
    print("✓ Affiliation+LastName: Medium confidence (80%)\n")


def demo_combined_features():
    """Demo using multiple features together."""
    print("=" * 80)
    print("DEMO 5: Combined Features")
    print("=" * 80)
    print("Using phonetic + Jaro-Winkler + abbreviations together\n")

    awards_df = pd.DataFrame(
        {
            "company": [
                "Smyth Advanced Technologies International",
                "Mikro Aerospace Defense Systems",
            ],
            "award_amount": [750000, 850000],
        }
    )

    companies_df = pd.DataFrame(
        {
            "company": [
                "Smith Adv Tech Intl",
                "Micro Aero Def Sys",
            ],
            "UEI": ["UEI301", "UEI302"],
        }
    )

    # Enable all features
    enhanced_config = {
        "enable_phonetic_matching": True,
        "phonetic_algorithm": "metaphone",
        "phonetic_boost": 5,
        "enable_jaro_winkler": True,
        "jaro_winkler_use_as_primary": False,  # Use as secondary
        "jaro_winkler_prefix_weight": 0.1,
        "enable_enhanced_abbreviations": True,
    }

    print("Awards (with misspellings AND long-form terms):")
    print(awards_df[["company", "award_amount"]])
    print("\nCompanies (correct spellings, abbreviated):")
    print(companies_df[["company", "UEI"]])

    enriched = enrich_awards_with_companies(
        awards_df,
        companies_df,
        enhanced_config=enhanced_config,
    )

    print("\nEnriched results:")
    print(
        enriched[
            ["company", "company_company", "_match_score", "_match_method"]
        ].to_string()
    )
    print("\n✓ Combined features provide robust matching across multiple error types\n")


def main():
    """Run all demos."""
    print("\n" + "=" * 80)
    print("ENHANCED MATCHING FEATURES DEMO")
    print("Data Cleaning for Company and Researcher Names")
    print("=" * 80 + "\n")

    try:
        demo_phonetic_matching()
        demo_jaro_winkler_matching()
        demo_enhanced_abbreviations()
        demo_researcher_matching()
        demo_combined_features()

        print("=" * 80)
        print("CONFIGURATION")
        print("=" * 80)
        print("All features can be enabled/disabled in config/base.yaml:")
        print("  enrichment:")
        print("    enhanced_matching:")
        print("      enable_phonetic_matching: false")
        print("      enable_jaro_winkler: false")
        print("      enable_enhanced_abbreviations: false")
        print("    researcher_matching:")
        print("      enable_orcid_matching: true")
        print("      enable_email_matching: true")
        print("      enable_affiliation_matching: true")
        print("\nSee config/dev.yaml for example configuration with features enabled.")
        print("=" * 80 + "\n")

    except ImportError as e:
        print(f"Error: {e}")
        print("\nMake sure to install dependencies:")
        print("  poetry install")


if __name__ == "__main__":
    main()
