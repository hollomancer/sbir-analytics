#!/usr/bin/env python3
"""Benchmark the transition detection pipeline outside of pytest.

This script generates a synthetic SBIR awards + contracts dataset, runs the
TransitionDetector end-to-end in batches, and emits throughput plus detection
metrics. Use it inside the Dagster/Docker environment when validating large
changes instead of running the heavy pytest-based simulations.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

from src.transition.detection.detector import TransitionDetector
from src.transition.performance.monitoring import PerformanceProfiler, profile_detection_performance


def build_transition_dataset(sample_size: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate synthetic awards/contracts similar to FY2020-2024 workloads."""
    cet_areas = ["AI", "Advanced Manufacturing", "Biotech", "Quantum", "Microelectronics"]
    agencies = ["NSF", "DoD", "DOE", "NIH", "NASA"]

    awards = pd.DataFrame(
        {
            "award_id": [f"SBIR-{2020 + (i % 5)}-{i:06d}" for i in range(sample_size)],
            "company": [f"Company {i}" for i in range(sample_size)],
            "UEI": [f"UEI{i:09d}" for i in range(sample_size)],
            "Phase": ["I" if i % 2 == 0 else "II" for i in range(sample_size)],
            "awarding_agency_name": [agencies[i % len(agencies)] for i in range(sample_size)],
            "award_date": pd.date_range("2020-01-01", periods=sample_size, freq="12H"),
            "completion_date": pd.date_range("2021-01-01", periods=sample_size, freq="12H"),
            "cet_area": [cet_areas[i % len(cet_areas)] for i in range(sample_size)],
            "award_amount": [100000 * (1 + (i % 50)) for i in range(sample_size)],
        }
    )

    contracts = pd.DataFrame(
        {
            "contract_id": [f"CONTRACT-{i:06d}" for i in range(sample_size * 2)],
            "vendor_uei": [awards.iloc[i % sample_size]["UEI"] for i in range(sample_size * 2)],
            "action_date": pd.date_range("2021-06-01", periods=sample_size * 2, freq="6H"),
            "description": [f"Contract {i}" for i in range(sample_size * 2)],
            "awarding_agency_name": [agencies[i % len(agencies)] for i in range(sample_size * 2)],
            "amount": [50000 * (1 + (i % 20)) for i in range(sample_size * 2)],
        }
    )

    return awards, contracts


def run_transition_detection_benchmark(
    sample_size: int,
    batch_size: int,
    score_threshold: float,
    extrapolation_target: int,
) -> dict[str, Any]:
    """Execute the TransitionDetector in batches and collect metrics."""
    awards, contracts = build_transition_dataset(sample_size)
    detector = TransitionDetector()
    profiler = PerformanceProfiler()

    logger.info("Starting benchmark: %s awards, batch size %s", len(awards), batch_size)

    detections: list[dict] = []
    start_time = time.time()

    for i in range(0, len(awards), batch_size):
        batch = awards.iloc[i : i + batch_size]
        batch_start = time.time()

        for _, award in batch.iterrows():
            try:
                records = detector.detect_transitions_for_award(
                    award_dict=award.to_dict(),
                    contracts_df=contracts,
                    score_threshold=score_threshold,
                )
                detections.extend(records)
            except Exception as exc:  # pragma: no cover - benchmarking diagnostics
                logger.warning("Detection failed for %s: %s", award["award_id"], exc)

        profiler.record_timing("batch_processing_ms", (time.time() - batch_start) * 1000)

    duration_seconds = time.time() - start_time
    profiler.record_count("total_detections", len(detections))
    profiler_summary = profiler.get_summary()

    extrapolated = int(len(detections) * (extrapolation_target / max(len(awards), 1)))
    perf_metrics = profile_detection_performance(
        awards_count=len(awards),
        contracts_count=len(contracts),
        detections_count=len(detections),
        total_time_ms=duration_seconds * 1000,
    )

    return {
        "sample_size": len(awards),
        "batch_size": batch_size,
        "score_threshold": score_threshold,
        "duration_seconds": duration_seconds,
        "detections_found": len(detections),
        "metrics": perf_metrics,
        "extrapolated": {
            "target_awards": extrapolation_target,
            "estimated_detections": extrapolated,
        },
        "profiler": profiler_summary,
    }


def save_benchmark(benchmark_data: dict[str, Any], output_path: Path | None) -> Path:
    """Persist benchmark JSON for regression tracking."""
    if output_path is None:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        output_path = Path("reports/benchmarks") / f"transition_detection_{timestamp}.json"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    benchmark_data["timestamp"] = datetime.utcnow().isoformat()

    with output_path.open("w") as handle:
        json.dump(benchmark_data, handle, indent=2, default=str)

    logger.info("Benchmark written to %s", output_path)
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark transition detection throughput.")
    parser.add_argument(
        "--sample-size", type=int, default=5000, help="Number of awards to simulate."
    )
    parser.add_argument(
        "--batch-size", type=int, default=250, help="Batch size for detector invocations."
    )
    parser.add_argument(
        "--score-threshold", type=float, default=0.5, help="Detector score threshold."
    )
    parser.add_argument(
        "--extrapolation-target",
        type=int,
        default=252_000,
        help="Awards count used for extrapolating detections.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path for benchmark JSON output.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    logger.info("=" * 80)
    logger.info("Transition Detection Benchmark")
    logger.info("Sample size: %s awards", args.sample_size)
    logger.info("Batch size : %s", args.batch_size)
    logger.info("=" * 80)

    results = run_transition_detection_benchmark(
        sample_size=args.sample_size,
        batch_size=args.batch_size,
        score_threshold=args.score_threshold,
        extrapolation_target=args.extrapolation_target,
    )
    save_benchmark(results, args.output)

    metrics = results["metrics"]
    logger.info("Detections found: %s", results["detections_found"])
    logger.info("Duration (s): %.2f", results["duration_seconds"])
    logger.info(
        "Throughput: %.0f detections/minute (target >= 10000)",
        metrics.get("detections_per_minute", 0),
    )
    logger.info(
        "Extrapolated detections for %s awards: %s",
        results["extrapolated"]["target_awards"],
        results["extrapolated"]["estimated_detections"],
    )


if __name__ == "__main__":  # pragma: no cover - manual execution
    main()
