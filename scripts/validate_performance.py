#!/usr/bin/env python3
"""
Performance validation script for transition detection system.

Tests that the system meets the ≥10K detections/minute target.
"""

import time
from datetime import date, timedelta

from src.models.transition_models import CompetitionType, FederalContract
from src.transition.detection.detector import TransitionDetector
from src.transition.features.vendor_resolver import VendorRecord, VendorResolver


def create_config():
    """Create configuration for performance testing."""
    return {
        "base_score": 0.15,
        "timing_window": {"min_days_after_completion": 0, "max_days_after_completion": 730},
        "confidence_thresholds": {"high": 0.85, "likely": 0.65},
        "scoring": {
            "agency_continuity": {"weight": 0.25, "enabled": True},
            "timing_alignment": {"weight": 0.20, "enabled": True},
            "competition_type": {"weight": 0.15, "enabled": True},
            "patent_signals": {"weight": 0.20, "enabled": False},
            "cet_alignment": {"weight": 0.15, "enabled": False},
            "text_similarity": {"weight": 0.05, "enabled": False},
        },
        "vendor_matching": {"require_match": True, "fuzzy_threshold": 0.8},
    }


def create_performance_dataset(num_awards=1000, num_contracts=5000):
    """Create larger dataset for performance testing."""

    # Generate awards
    awards = []
    for i in range(num_awards):
        awards.append(
            {
                "award_id": f"SBIR-{i:06d}",
                "company": f"Company {i % 100}",  # Reuse company names for matching
                "vendor_uei": f"UEI{i % 100:09d}",  # Reuse UEIs for matching
                "agency": ["DOD", "NSF", "NIH", "DOE", "NASA"][i % 5],
                "completion_date": date(2020, 1, 1) + timedelta(days=i % 365),
                "phase": "I" if i % 2 == 0 else "II",
            }
        )

    # Generate contracts
    contracts = []
    for i in range(num_contracts):
        contracts.append(
            FederalContract(
                contract_id=f"CONTRACT-{i:06d}",
                agency=["DOD", "NSF", "NIH", "DOE", "NASA"][i % 5],
                vendor_name=f"Company {i % 100}",
                vendor_uei=f"UEI{i % 100:09d}",
                start_date=date(2021, 1, 1) + timedelta(days=i % 365),
                obligation_amount=float(100000 + (i % 900000)),
                competition_type=[CompetitionType.SOLE_SOURCE, CompetitionType.FULL_AND_OPEN][
                    i % 2
                ],
                description=f"Contract {i} description",
            )
        )

    return awards, contracts


def create_vendor_resolver(awards):
    """Create vendor resolver from awards."""
    vendor_records = []
    seen_ueis = set()

    for award in awards:
        uei = award.get("vendor_uei")
        if uei and uei not in seen_ueis:
            vendor_records.append(
                VendorRecord(
                    uei=uei,
                    cage=None,
                    duns=None,
                    name=award.get("company"),
                    metadata={"award_id": award["award_id"]},
                )
            )
            seen_ueis.add(uei)

    return VendorResolver.from_records(vendor_records)


def measure_throughput(detector, awards, contracts, target_detections=10000):
    """Measure detection throughput."""
    print(f"🚀 Performance Test: Target {target_detections:,} detections")
    print(f"   Dataset: {len(awards):,} awards, {len(contracts):,} contracts")

    start_time = time.time()
    total_detections = 0

    # Process awards until we hit target or run out
    for i, award in enumerate(awards):
        if total_detections >= target_detections:
            break

        detections = detector.detect_for_award(award=award, candidate_contracts=contracts)
        total_detections += len(detections)

        # Progress update every 100 awards
        if (i + 1) % 100 == 0:
            elapsed = time.time() - start_time
            rate = total_detections / (elapsed / 60) if elapsed > 0 else 0
            print(
                f"   Processed {i+1:,} awards, {total_detections:,} detections, {rate:,.0f} det/min"
            )

    end_time = time.time()
    elapsed_minutes = (end_time - start_time) / 60

    return {
        "total_detections": total_detections,
        "elapsed_minutes": elapsed_minutes,
        "detections_per_minute": total_detections / elapsed_minutes if elapsed_minutes > 0 else 0,
        "awards_processed": i + 1,
    }


def main():
    """Run performance validation."""
    print("⚡ Transition Detection Performance Validation")
    print("=" * 50)

    # Create test data
    print("📊 Creating performance test dataset...")
    awards, contracts = create_performance_dataset(num_awards=500, num_contracts=2000)
    vendor_resolver = create_vendor_resolver(awards)

    print(f"✓ Created dataset: {len(awards):,} awards, {len(contracts):,} contracts")

    # Initialize detector
    config = create_config()
    detector = TransitionDetector(config=config, vendor_resolver=vendor_resolver)
    print("✓ Initialized detector")

    # Run performance test
    target = 10000  # Target: 10K detections
    results = measure_throughput(detector, awards, contracts, target)

    # Results
    print("\n📈 Performance Results:")
    print(f"   Total detections: {results['total_detections']:,}")
    print(f"   Time elapsed: {results['elapsed_minutes']:.2f} minutes")
    print(f"   Throughput: {results['detections_per_minute']:,.0f} detections/minute")
    print(f"   Awards processed: {results['awards_processed']:,}")

    # Validation
    target_rate = 10000  # 10K detections/minute
    meets_target = results["detections_per_minute"] >= target_rate

    print("\n🎯 Performance Target Validation:")
    print(f"   Target: ≥{target_rate:,} detections/minute")
    print(f"   Actual: {results['detections_per_minute']:,.0f} detections/minute")
    print(f"   Status: {'✅ PASSED' if meets_target else '❌ FAILED'}")

    if meets_target:
        print(
            f"   Performance exceeds target by {results['detections_per_minute'] - target_rate:,.0f} det/min"
        )
    else:
        shortfall = target_rate - results["detections_per_minute"]
        print(f"   Performance shortfall: {shortfall:,.0f} det/min")

    # Memory usage (basic check)
    import os

    import psutil

    process = psutil.Process(os.getpid())
    memory_mb = process.memory_info().rss / 1024 / 1024

    print("\n💾 Memory Usage:")
    print(f"   Current usage: {memory_mb:.1f} MB")
    print(
        f"   Status: {'✅ EFFICIENT' if memory_mb < 500 else '⚠️ HIGH' if memory_mb < 1000 else '❌ EXCESSIVE'}"
    )

    return meets_target


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
