"""Consolidated test fixtures and data generators.

This module provides reusable fixtures and data generators for tests across the codebase,
reducing duplication and ensuring consistency.

Usage:
    from tests.utils.fixtures import create_sample_sbir_data, create_sample_cet_area

    def test_my_feature():
        df = create_sample_sbir_data(num_records=10)
        # ...
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd

from src.models.cet_models import CETArea, EvidenceStatement


def create_sample_sbir_data(num_records: int = 3) -> pd.DataFrame:
    """Create sample SBIR awards data for testing.

    Args:
        num_records: Number of records to generate

    Returns:
        DataFrame with sample SBIR award data
    """
    records = []
    companies = ["Acme Innovations Inc", "BioTech Labs LLC", "NanoWorks Corporation"]
    ueis = ["A1B2C3D4E5F6G7H8", "", ""]
    duns = ["123456789", "987654321", ""]
    contracts = ["C-2023-0001", "C-2023-0002", "C-2023-0003"]
    titles = [
        "Advanced Widget Development",
        "Biotech Research Platform",
        "Nanotechnology Solutions",
    ]

    for i in range(num_records):
        idx = i % len(companies)
        records.append(
            {
                "Company": companies[idx],
                "UEI": ueis[idx] if i < len(ueis) else "",
                "Duns": duns[idx] if i < len(duns) else "",
                "Contract": contracts[idx] if i < len(contracts) else f"C-2023-{i:04d}",
                "Award Title": titles[idx] if i < len(titles) else f"Test Award {i}",
            }
        )

    return pd.DataFrame(records)


def create_sample_cet_area(
    cet_id: str = "artificial_intelligence",
    name: str | None = None,
    taxonomy_version: str = "NSTC-2025Q1",
) -> CETArea:
    """Create a sample CET area for testing.

    Args:
        cet_id: CET area identifier
        name: CET area name (defaults based on cet_id)
        taxonomy_version: Taxonomy version

    Returns:
        CETArea instance
    """
    if name is None:
        name_map = {
            "artificial_intelligence": "Artificial Intelligence",
            "quantum_information_science": "Quantum Information Science",
            "autonomous_systems": "Autonomous Systems",
            "biotechnologies": "Biotechnologies",
        }
        name = name_map.get(cet_id, f"Test CET Area {cet_id}")

    return CETArea(
        cet_id=cet_id,
        name=name,
        definition=f"Test definition for {name}",
        keywords=["test", "keyword", "example"],
        taxonomy_version=taxonomy_version,
    )


def create_sample_evidence_statement(
    excerpt: str | None = None,
    source_location: str = "abstract",
) -> EvidenceStatement:
    """Create a sample evidence statement for testing.

    Args:
        excerpt: Evidence excerpt text
        source_location: Source location (abstract, title, etc.)

    Returns:
        EvidenceStatement instance
    """
    if excerpt is None:
        excerpt = "This project develops machine learning algorithms for pattern recognition"

    return EvidenceStatement(
        excerpt=excerpt,
        source_location=source_location,
        rationale_tag=f"Contains: {excerpt[:30]}...",
    )


def create_sample_award_data(
    award_id: str = "award_001",
    title: str | None = None,
    abstract: str | None = None,
) -> dict[str, Any]:
    """Create sample SBIR award data dictionary.

    Args:
        award_id: Award identifier
        title: Award title
        abstract: Award abstract

    Returns:
        Dictionary with award data
    """
    if title is None:
        title = "Advanced Machine Learning for Pattern Recognition"
    if abstract is None:
        abstract = (
            "This project develops novel machine learning algorithms using deep neural networks "
            "for automated pattern recognition in large-scale datasets."
        )

    return {
        "award_id": award_id,
        "title": title,
        "abstract": abstract,
        "keywords": ["machine learning", "deep learning", "pattern recognition", "neural networks"],
        "agency": "DOD",
        "phase": "II",
        "award_amount": 750000.0,
        "award_date": "2024-01-15",
    }


def create_sample_contract_data(
    contract_id: str = "contract_001",
    company_name: str = "Test Company Inc",
    uei: str = "TEST123456789",
) -> dict[str, Any]:
    """Create sample contract data dictionary.

    Args:
        contract_id: Contract identifier
        company_name: Company name
        uei: Company UEI

    Returns:
        Dictionary with contract data
    """
    return {
        "contract_id": contract_id,
        "company_name": company_name,
        "uei": uei,
        "duns": "123456789",
        "award_amount": 100000.0,
        "award_date": date(2023, 1, 15),
        "agency": "DOD",
    }


def create_sample_transitions_df(num_transitions: int = 5) -> pd.DataFrame:
    """Create sample transition detections DataFrame.

    Args:
        num_transitions: Number of transitions to generate

    Returns:
        DataFrame with transition detection data
    """
    records = []
    for i in range(num_transitions):
        records.append(
            {
                "transition_id": f"trans_{i:03d}",
                "award_id": f"award_{i:03d}",
                "contract_id": f"contract_{i:03d}",
                "likelihood_score": 75.0 + (i * 5),
                "confidence": ["high", "likely", "possible"][i % 3],
                "detected_at": datetime(2024, 1, 15 + i),
            }
        )
    return pd.DataFrame(records)


def create_sample_enriched_awards_df(num_awards: int = 10) -> pd.DataFrame:
    """Create sample enriched SBIR awards DataFrame.

    Args:
        num_awards: Number of awards to generate

    Returns:
        DataFrame with enriched award data
    """
    records = []
    agencies = ["NSF", "DOD", "NIH", "DOE", "NASA"]
    states = ["CA", "TX", "NY", "FL", "MA"]
    cities = ["San Francisco", "Austin", "New York", "Miami", "Boston"]

    for i in range(num_awards):
        records.append(
            {
                "award_id": f"A{i:03d}",
                "company_name": f"Company {i}",
                "award_amount": 100000.0 + (i * 10000),
                "award_date": date(2023, (i % 12) + 1, 15),
                "company_state": states[i % len(states)],
                "agency": agencies[i % len(agencies)],
                "company_uei": f"UEI-{i:06d}",
                "company_city": cities[i % len(cities)],
                "company_zip": f"9{i:04d}",
            }
        )
    return pd.DataFrame(records)

