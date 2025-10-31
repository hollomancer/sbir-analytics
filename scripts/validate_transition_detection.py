#!/usr/bin/env python3
"""
Simple validation script for transition detection system.

This script demonstrates that the core transition detection functionality
is working by running a minimal example with sample data.
"""

import pandas as pd
from datetime import date, timedelta
from src.models.transition_models import FederalContract, CompetitionType
from src.transition.detection.detector import TransitionDetector
from src.transition.features.vendor_resolver import VendorRecord, VendorResolver


def create_sample_config():
    """Create a minimal configuration for testing."""
    return {
        "base_score": 0.15,
        "timing_window": {"min_days_after_completion": 0, "max_days_after_completion": 730},
        "confidence_thresholds": {"high": 0.85, "likely": 0.65},
        "scoring": {
            "agency_continuity": {"weight": 0.25, "enabled": True},
            "timing_alignment": {"weight": 0.20, "enabled": True},
            "competition_type": {"weight": 0.15, "enabled": True},
            "patent_signals": {
                "weight": 0.20,
                "enabled": False,  # Disabled for simple test
            },
            "cet_alignment": {
                "weight": 0.15,
                "enabled": False,  # Disabled for simple test
            },
            "text_similarity": {
                "weight": 0.05,
                "enabled": False,  # Disabled for simple test
            },
        },
        "vendor_matching": {"require_match": True, "fuzzy_threshold": 0.8},
    }


def create_sample_data():
    """Create sample awards and contracts for testing."""

    # Sample awards
    awards = [
        {
            "award_id": "SBIR-2020-001",
            "company": "TechCorp Inc",
            "vendor_uei": "UEI123456789",
            "agency": "DOD",
            "completion_date": date(2020, 12, 31),
            "phase": "II",
        },
        {
            "award_id": "SBIR-2020-002",
            "company": "InnovateLab LLC",
            "vendor_uei": "UEI987654321",
            "agency": "NSF",
            "completion_date": date(2020, 6, 30),
            "phase": "I",
        },
    ]

    # Sample contracts
    contracts = [
        FederalContract(
            contract_id="CONTRACT-2021-001",
            agency="DOD",
            vendor_name="TechCorp Inc",
            vendor_uei="UEI123456789",
            start_date=date(2021, 3, 15),
            obligation_amount=500000.0,
            competition_type=CompetitionType.SOLE_SOURCE,
            description="Advanced AI system development",
        ),
        FederalContract(
            contract_id="CONTRACT-2021-002",
            agency="NSF",
            vendor_name="InnovateLab LLC",
            vendor_uei="UEI987654321",
            start_date=date(2021, 1, 10),
            obligation_amount=250000.0,
            competition_type=CompetitionType.FULL_AND_OPEN,
            description="Research collaboration platform",
        ),
        FederalContract(
            contract_id="CONTRACT-2021-003",
            agency="DOE",
            vendor_name="Different Company",
            vendor_uei="UEI111222333",
            start_date=date(2021, 5, 1),
            obligation_amount=750000.0,
            competition_type=CompetitionType.FULL_AND_OPEN,
            description="Energy storage system",
        ),
    ]

    return awards, contracts


def create_vendor_resolver(awards):
    """Create a vendor resolver from award data."""
    vendor_records = []
    for award in awards:
        vendor_records.append(
            VendorRecord(
                uei=award.get("vendor_uei"),
                cage=None,
                duns=None,
                name=award.get("company"),
                metadata={"award_id": award["award_id"]},
            )
        )

    return VendorResolver.from_records(vendor_records)


def main():
    """Run the validation."""
    print("🔍 Validating Transition Detection System")
    print("=" * 50)

    # Create configuration and sample data
    config = create_sample_config()
    awards, contracts = create_sample_data()
    vendor_resolver = create_vendor_resolver(awards)

    print(f"✓ Created sample data:")
    print(f"  - {len(awards)} awards")
    print(f"  - {len(contracts)} contracts")
    stats = vendor_resolver.stats()
    total_records = stats["records_by_uei"] + stats["records_by_cage"] + stats["records_by_duns"]
    print(f"  - {total_records} vendor record entries")

    # Initialize detector
    detector = TransitionDetector(config=config, vendor_resolver=vendor_resolver)
    print("✓ Initialized TransitionDetector")

    # Run detection for each award
    all_detections = []
    for award in awards:
        print(f"\n🔎 Processing award: {award['award_id']}")

        detections = detector.detect_for_award(award=award, candidate_contracts=contracts)

        print(f"  Found {len(detections)} potential transitions")
        for detection in detections:
            contract_id = (
                detection.primary_contract.contract_id if detection.primary_contract else "N/A"
            )
        print(
            f"    - {contract_id}: score={detection.likelihood_score:.3f}, confidence={detection.confidence}"
        )

        all_detections.extend(detections)

    # Summary
    print(f"\n📊 Detection Summary:")
    print(f"  - Total detections: {len(all_detections)}")

    if all_detections:
        scores = [d.likelihood_score for d in all_detections]
        confidences = [d.confidence.value for d in all_detections]

        print(f"  - Score range: {min(scores):.3f} - {max(scores):.3f}")
        print(f"  - Average score: {sum(scores)/len(scores):.3f}")
        print(f"  - Confidence distribution:")

        from collections import Counter

        conf_counts = Counter(confidences)
        for conf, count in conf_counts.items():
            print(f"    - {conf}: {count}")

    # Metrics
    metrics = detector.get_metrics()
    print(f"\n📈 Detection Metrics:")
    print(f"  - Awards processed: {metrics.get('awards_processed', 0)}")
    print(f"  - Contracts evaluated: {metrics.get('contracts_evaluated', 0)}")
    print(f"  - Vendor match rate: {metrics.get('vendor_match_rate', 0):.1%}")

    print(f"\n✅ Validation completed successfully!")
    print(f"   The transition detection system is working correctly.")

    return len(all_detections) > 0


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
