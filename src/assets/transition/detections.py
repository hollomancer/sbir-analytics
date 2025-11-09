"""Transition detections assets.

This module contains:
- transformed_transition_detections: Flag high-confidence transitions
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .utils import (
    Output,
    TransitionDetectionAnalyzer,
    _env_float,
    asset,
    now_utc_iso,
    save_dataframe_parquet,
)


@asset(
    name="transformed_transition_detections",
    group_name="transformation",
    compute_kind="pandas",
    description=(
        "Consolidated transition detections derived from transition_scores_v1. "
        "Writes parquet and logs basic metrics."
    ),
)
def transformed_transition_detections(
    context,
    transformed_transition_scores: pd.DataFrame,
) -> Output[pd.DataFrame]:
    out_path = Path("data/processed/transition_detections.parquet")

    # Start from the scored candidates; ensure core columns exist
    df = transformed_transition_scores.copy()
    required_cols = ["award_id", "contract_id", "score", "method", "computed_at"]
    for c in required_cols:
        if c not in df.columns:
            df[c] = None

    # Metrics
    threshold = _env_float("SBIR_ETL__TRANSITION__ANALYTICS__SCORE_THRESHOLD", 0.60)
    scores = (
        pd.to_numeric(df["score"], errors="coerce").fillna(0.0)
        if "score" in df.columns
        else pd.Series([], dtype=float)  # type: ignore
    )
    total = int(len(df))
    high_conf = int((scores >= threshold).sum()) if total > 0 else 0
    avg_score = float(scores.mean()) if total > 0 else 0.0
    by_method = (
        df["method"].value_counts(dropna=False).to_dict()
        if "method" in df.columns and total > 0
        else {}
    )

    # Persist detections table
    save_dataframe_parquet(df, out_path)

    # Log and return with metadata
    metrics = {
        "generated_at": now_utc_iso(),
        "total_candidates": total,
        "high_confidence_candidates": high_conf,
        "avg_score": round(avg_score, 6),
        "threshold": float(threshold),
        "by_method": by_method,
    }
    context.log.info("Produced transition_detections", extra=metrics)

    # Initialize metadata dict
    meta = {
        "output_path": str(out_path),
        "rows": total,
        "high_confidence_candidates": high_conf,
        "avg_score": avg_score,
        "threshold": float(threshold),
        "by_method": by_method,
    }

    # Perform statistical analysis with transition analyzer
    if TransitionDetectionAnalyzer is not None:
        try:
            analyzer = TransitionDetectionAnalyzer()
            run_context = {
                "run_id": context.run.run_id if context.run else f"run_{context.run_id}",
                "pipeline_name": "transition_detection",
                "stage": "detect",
            }

            # Prepare module data for analysis
            module_data = {
                "transitions_df": df,
                "detection_results": {
                    "awards_processed": total,
                    "detection_failed": 0,  # Could be enhanced with actual failure counts
                    "duration_seconds": 0.0,  # Could be enhanced with actual timing
                    "records_per_second": 0.0,  # Could be enhanced with actual throughput
                },
                "run_context": run_context,
            }

            # Generate analysis report
            analysis_report = analyzer.analyze(module_data)

            context.log.info(
                "Transition detection analysis complete",
                extra={
                    "insights_generated": len(analysis_report.insights)
                    if hasattr(analysis_report, "insights")
                    else 0,
                    "data_hygiene_score": analysis_report.data_hygiene.quality_score_mean
                    if analysis_report.data_hygiene
                    else None,
                    "transition_success_rate": analysis_report.success_rate,
                },
            )

            # Add analysis results to metadata
            meta.update(
                {
                    "analysis_insights_count": len(analysis_report.insights)
                    if hasattr(analysis_report, "insights")
                    else 0,
                    "analysis_data_hygiene_score": round(
                        analysis_report.data_hygiene.quality_score_mean, 3
                    )
                    if analysis_report.data_hygiene
                    else None,
                    "analysis_transition_rate": analysis_report.module_metrics.get(
                        "overall_transition_rate", 0
                    )
                    if analysis_report.module_metrics
                    else 0,
                    "analysis_sector_transition_rates": analysis_report.module_metrics.get(
                        "sector_transition_rates", {}
                    )
                    if analysis_report.module_metrics
                    else {},
                    "analysis_success_story_metrics": analysis_report.module_metrics.get(
                        "success_story_metrics", {}
                    )
                    if analysis_report.module_metrics
                    else {},
                    "analysis_signal_strength_metrics": analysis_report.module_metrics.get(
                        "signal_strength_metrics", {}
                    )
                    if analysis_report.module_metrics
                    else {},
                }
            )

        except Exception as e:
            context.log.warning(f"Transition detection analysis failed: {e}")
    else:
        context.log.info("Transition analyzer not available; skipping statistical analysis")

    return Output(df, metadata=meta)
