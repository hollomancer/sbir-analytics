"""Transition detection analyzer for statistical reporting.

This analyzer focuses on transition detection operations, calculating technology
transition success rates by sector, generating commercialization pattern analysis,
and identifying high-impact transition examples for success stories.
"""

from typing import Any

import pandas as pd
from loguru import logger

from src.models.quality import ChangesSummary, DataHygieneMetrics, ModuleReport
from src.utils.reporting.analyzers.base_analyzer import AnalysisInsight, ModuleAnalyzer


class TransitionDetectionAnalyzer(ModuleAnalyzer):
    """Analyzer for transition detection operations and commercialization success."""

    def __init__(self, config: dict[str, Any] | None = None):
        """Initialize transition detection analyzer.

        Args:
            config: Optional configuration for analysis thresholds
        """
        super().__init__("transition_detection", config)

        # Default thresholds - can be overridden by config
        self.thresholds = {
            "min_transition_rate": self.config.get("min_transition_rate", 0.05),
            "min_high_confidence_rate": self.config.get("min_high_confidence_rate", 0.30),
            "min_success_story_score": self.config.get("min_success_story_score", 0.80),
            "max_failed_detection_rate": self.config.get("max_failed_detection_rate", 0.20),
            "min_signal_strength": self.config.get("min_signal_strength", 0.60),
        }

        # Transition confidence bands
        self.confidence_bands = {"high": (0.8, 1.0), "likely": (0.6, 0.79), "possible": (0.0, 0.59)}

        # Key sectors for analysis
        self.key_sectors = [
            "defense",
            "health",
            "energy",
            "transportation",
            "information_technology",
            "aerospace",
            "biotechnology",
            "manufacturing",
            "research",
            "other",
        ]

    def analyze(self, module_data: dict[str, Any]) -> ModuleReport:
        """Analyze transition detection data and generate comprehensive report.

        Args:
            module_data: Dictionary containing:
                - transitions_df: DataFrame with detected transitions
                - awards_df: Original awards DataFrame
                - detection_results: Detection operation results
                - run_context: Pipeline run context

        Returns:
            ModuleReport with transition detection analysis
        """
        logger.info("Starting transition detection analysis")

        transitions_df = module_data.get("transitions_df")
        awards_df = module_data.get("awards_df")
        detection_results = module_data.get("detection_results", {})
        run_context = module_data.get("run_context", {})

        if transitions_df is None:
            logger.warning("No transitions DataFrame provided for analysis")
            return self._create_empty_report(run_context)

        # Calculate key metrics
        key_metrics = self.get_key_metrics(module_data)

        # Generate insights
        insights = self.generate_insights(module_data)

        # Calculate data hygiene metrics
        data_hygiene = self._calculate_data_hygiene(transitions_df, awards_df)

        # Calculate changes summary
        changes_summary = self._calculate_changes_summary(transitions_df, awards_df)

        # Extract processing metrics
        total_records = len(awards_df) if awards_df is not None else 0
        records_processed = detection_results.get("awards_processed", total_records)
        records_failed = detection_results.get("detection_failed", 0)
        duration_seconds = detection_results.get("duration_seconds", 0.0)

        # Create module report
        report = self.create_module_report(
            run_id=run_context.get("run_id", "unknown"),
            stage="detect",
            total_records=total_records,
            records_processed=records_processed,
            records_failed=records_failed,
            duration_seconds=duration_seconds,
            module_metrics=key_metrics,
            data_hygiene=data_hygiene,
            changes_summary=changes_summary,
        )

        logger.info(f"Transition detection analysis complete: {len(insights)} insights generated")
        return report

    def get_key_metrics(self, module_data: dict[str, Any]) -> dict[str, Any]:
        """Extract key metrics from transition detection data.

        Args:
            module_data: Module data containing transitions and awards DataFrames

        Returns:
            Dictionary of key transition detection metrics
        """
        transitions_df = module_data.get("transitions_df")
        awards_df = module_data.get("awards_df")
        detection_results = module_data.get("detection_results", {})

        if transitions_df is None or awards_df is None:
            return {"error": "Missing transitions or awards DataFrame"}

        total_awards = len(awards_df)
        total_transitions = len(transitions_df)

        # Calculate overall transition rate
        transition_rate = total_transitions / total_awards if total_awards > 0 else 0

        # Calculate confidence distribution
        confidence_distribution = self._calculate_confidence_distribution(transitions_df)

        # Calculate sector transition rates
        sector_transition_rates = self._calculate_sector_transition_rates(transitions_df, awards_df)

        # Calculate commercialization patterns
        commercialization_patterns = self._calculate_commercialization_patterns(transitions_df)

        # Calculate success story metrics
        success_story_metrics = self._calculate_success_story_metrics(transitions_df)

        # Calculate signal strength metrics
        signal_strength_metrics = self._calculate_signal_strength_metrics(transitions_df)

        # Calculate timing analysis
        timing_analysis = self._calculate_timing_analysis(transitions_df)

        return {
            "total_awards": total_awards,
            "total_transitions": total_transitions,
            "overall_transition_rate": transition_rate,
            "confidence_distribution": confidence_distribution,
            "sector_transition_rates": sector_transition_rates,
            "commercialization_patterns": commercialization_patterns,
            "success_story_metrics": success_story_metrics,
            "signal_strength_metrics": signal_strength_metrics,
            "timing_analysis": timing_analysis,
            "processing_duration_seconds": detection_results.get("duration_seconds", 0.0),
            "detection_throughput": detection_results.get("records_per_second", 0.0),
        }

    def generate_insights(self, module_data: dict[str, Any]) -> list[AnalysisInsight]:
        """Generate automated insights for transition detection analysis.

        Args:
            module_data: Module data containing transitions and awards DataFrames

        Returns:
            List of analysis insights and recommendations
        """
        insights: list[Any] = []
        transitions_df = module_data.get("transitions_df")
        awards_df = module_data.get("awards_df")
        module_data.get("detection_results", {})

        if transitions_df is None or awards_df is None:
            return insights

        total_awards = len(awards_df)
        total_transitions = len(transitions_df)
        transition_rate = total_transitions / total_awards if total_awards > 0 else 0

        # Analyze overall transition rate
        if transition_rate < self.thresholds["min_transition_rate"]:
            insights.append(
                AnalysisInsight(
                    category="transition_rate",
                    title="Low Overall Transition Rate",
                    message=f"Transition rate ({transition_rate:.1%}) is below threshold ({self.thresholds['min_transition_rate']:.1%})",
                    severity="warning",
                    confidence=0.9,
                    affected_records=total_awards,
                    recommendations=[
                        "Review detection algorithm sensitivity",
                        "Check data quality for transition signals",
                        "Consider expanding timing windows",
                        "Validate vendor matching accuracy",
                    ],
                    metadata={
                        "current_rate": transition_rate,
                        "threshold": self.thresholds["min_transition_rate"],
                    },
                )
            )

        # Analyze confidence distribution
        confidence_dist = self._calculate_confidence_distribution(transitions_df)
        high_confidence_rate = confidence_dist.get("high_confidence_rate", 0.0)
        if high_confidence_rate < self.thresholds["min_high_confidence_rate"]:
            insights.append(
                AnalysisInsight(
                    category="confidence_distribution",
                    title="Low High-Confidence Transition Rate",
                    message=f"High-confidence transitions ({high_confidence_rate:.1%}) below target ({self.thresholds['min_high_confidence_rate']:.1%})",
                    severity="info",
                    confidence=0.8,
                    affected_records=int(total_transitions * (1 - high_confidence_rate)),
                    recommendations=[
                        "Strengthen signal weighting in detection algorithm",
                        "Improve evidence quality thresholds",
                        "Review confidence calibration",
                        "Consider additional signal types",
                    ],
                    metadata={
                        "current_rate": high_confidence_rate,
                        "threshold": self.thresholds["min_high_confidence_rate"],
                    },
                )
            )

        # Analyze sector imbalances
        sector_rates = self._calculate_sector_transition_rates(transitions_df, awards_df)
        if sector_rates:
            max_rate = max(sector_rates.values())
            min_rate = min(sector_rates.values())
            imbalance_ratio = max_rate / min_rate if min_rate > 0 else float("inf")

            if imbalance_ratio > 5:  # Significant sector imbalance
                insights.append(
                    AnalysisInsight(
                        category="sector_imbalance",
                        title="Significant Sector Transition Imbalance",
                        message=f"Sector transition rates show imbalance (ratio: {imbalance_ratio:.1f}:1)",
                        severity="info",
                        confidence=0.7,
                        affected_records=total_awards,
                        recommendations=[
                            "Investigate sector-specific detection challenges",
                            "Review sector classification accuracy",
                            "Consider sector-specific algorithm tuning",
                            "Validate sector representation in training data",
                        ],
                        metadata={
                            "imbalance_ratio": imbalance_ratio,
                            "max_rate": max_rate,
                            "min_rate": min_rate,
                        },
                    )
                )

        # Analyze success story potential
        success_metrics = self._calculate_success_story_metrics(transitions_df)
        high_impact_count = success_metrics.get("high_impact_transitions", 0)
        if high_impact_count == 0:
            insights.append(
                AnalysisInsight(
                    category="success_stories",
                    title="No High-Impact Success Stories Identified",
                    message="No transitions meet success story criteria - may indicate overly strict thresholds",
                    severity="info",
                    confidence=0.6,
                    affected_records=total_transitions,
                    recommendations=[
                        "Review success story scoring criteria",
                        "Consider lowering impact thresholds",
                        "Validate impact metrics calculation",
                        "Check for data completeness issues",
                    ],
                    metadata={"high_impact_count": high_impact_count},
                )
            )

        # Analyze signal strength
        signal_metrics = self._calculate_signal_strength_metrics(transitions_df)
        avg_signal_strength = signal_metrics.get("average_signal_strength", 0.0)
        if avg_signal_strength < self.thresholds["min_signal_strength"]:
            insights.append(
                AnalysisInsight(
                    category="signal_strength",
                    title="Weak Average Signal Strength",
                    message=f"Average signal strength ({avg_signal_strength:.2f}) below threshold ({self.thresholds['min_signal_strength']:.2f})",
                    severity="warning",
                    confidence=0.8,
                    affected_records=total_transitions,
                    recommendations=[
                        "Review signal calculation logic",
                        "Improve feature engineering",
                        "Validate signal data sources",
                        "Consider alternative signal combinations",
                    ],
                    metadata={
                        "current_strength": avg_signal_strength,
                        "threshold": self.thresholds["min_signal_strength"],
                    },
                )
            )

        return insights

    def _calculate_confidence_distribution(self, transitions_df: pd.DataFrame) -> dict[str, Any]:
        """Calculate confidence level distribution for transitions.

        Args:
            transitions_df: DataFrame with transition detections

        Returns:
            Dictionary with confidence distribution metrics
        """
        total_transitions = len(transitions_df)
        if total_transitions == 0:
            return {"error": "No transitions available"}

        confidence_distribution: dict[str, int | float] = {}

        # Check for confidence/likelihood columns
        confidence_columns = ["confidence", "likelihood_score", "score", "confidence_level"]

        confidence_values = []
        for col in confidence_columns:
            if col in transitions_df.columns:
                if col == "confidence_level":
                    # Handle categorical confidence
                    confidence_counts = transitions_df[col].value_counts()
                    for level, count in confidence_counts.items():
                        level_str = str(level).lower()
                        confidence_distribution[f"{level_str}_count"] = int(count)
                        confidence_distribution[f"{level_str}_rate"] = count / total_transitions
                else:
                    # Handle numeric confidence
                    values = pd.to_numeric(transitions_df[col], errors="coerce").dropna()
                    confidence_values.extend(values.tolist())

        # Categorize numeric confidences into bands
        if confidence_values:
            confidence_series = pd.Series(confidence_values)

            high_confidence = (
                (confidence_series >= self.confidence_bands["high"][0])
                & (confidence_series <= self.confidence_bands["high"][1])
            ).sum()
            likely_confidence = (
                (confidence_series >= self.confidence_bands["likely"][0])
                & (confidence_series <= self.confidence_bands["likely"][1])
            ).sum()
            possible_confidence = (
                (confidence_series >= self.confidence_bands["possible"][0])
                & (confidence_series <= self.confidence_bands["possible"][1])
            ).sum()

            confidence_distribution.update(
                {
                    "high_confidence_count": int(high_confidence),
                    "likely_confidence_count": int(likely_confidence),
                    "possible_confidence_count": int(possible_confidence),
                    "high_confidence_rate": high_confidence / len(confidence_series),
                    "likely_confidence_rate": likely_confidence / len(confidence_series),
                    "possible_confidence_rate": possible_confidence / len(confidence_series),
                    "average_confidence": float(confidence_series.mean()),
                    "median_confidence": float(confidence_series.median()),
                }
            )

        return confidence_distribution

    def _calculate_sector_transition_rates(
        self, transitions_df: pd.DataFrame, awards_df: pd.DataFrame
    ) -> dict[str, float]:
        """Calculate transition rates by sector/agency.

        Args:
            transitions_df: DataFrame with transition detections
            awards_df: DataFrame with original awards

        Returns:
            Dictionary mapping sectors to transition rates
        """
        if awards_df is None or transitions_df is None:
            return {}  # type: ignore[unreachable]

        # Try to find sector/agency columns
        sector_columns = ["agency", "awarding_agency", "agency_name", "sector", "agency_code"]

        sector_col = None
        for col in sector_columns:
            if col in awards_df.columns:
                sector_col = col
                break

        if sector_col is None:
            return {"error": "No sector/agency column found"}

        # Get successful transitions by award_id
        successful_award_ids: set[Any] = set()
        award_id_columns = ["award_id", "award", "id"]
        for col in award_id_columns:
            if col in transitions_df.columns:
                successful_award_ids.update(transitions_df[col].dropna().astype(str))
                break

        # Calculate rates by sector
        sector_rates = {}
        for sector in awards_df[sector_col].dropna().unique():
            sector_awards = awards_df[awards_df[sector_col] == sector]
            sector_transitions = sum(
                1 for award_id in sector_awards.index if str(award_id) in successful_award_ids
            )

            if len(sector_awards) > 0:
                sector_rates[str(sector).lower()] = sector_transitions / len(sector_awards)

        return sector_rates

    def _calculate_commercialization_patterns(self, transitions_df: pd.DataFrame) -> dict[str, Any]:
        """Analyze patterns in successful commercializations.

        Args:
            transitions_df: DataFrame with transition detections

        Returns:
            Dictionary with commercialization pattern metrics
        """
        total_transitions = len(transitions_df)
        if total_transitions == 0:
            return {"error": "No transitions available"}

        patterns = {}

        # Analyze timing patterns
        timing_columns = ["days_between", "months_between", "timing_score"]
        for col in timing_columns:
            if col in transitions_df.columns:
                if "days" in col or "months" in col:
                    values = pd.to_numeric(transitions_df[col], errors="coerce").dropna()
                    patterns[f"{col}_distribution"] = {
                        "mean": float(values.mean()) if not values.empty else 0,
                        "median": float(values.median()) if not values.empty else 0,
                        "std": float(values.std()) if not values.empty else 0,
                    }
                elif "score" in col:
                    patterns[f"{col}_stats"] = {
                        "mean": float(transitions_df[col].mean()),
                        "median": float(transitions_df[col].median()),
                        "high_score_rate": (transitions_df[col] >= 0.8).mean(),
                    }

        # Analyze signal strength patterns
        signal_columns = ["agency_score", "competition_score", "patent_score", "cet_score"]
        for col in signal_columns:
            if col in transitions_df.columns:
                patterns[f"{col}_contribution"] = {
                    "mean": float(transitions_df[col].mean()),
                    "high_contribution_rate": (transitions_df[col] >= 0.7).mean(),
                }

        # Analyze competition types
        if "competition_type" in transitions_df.columns:
            competition_dist = transitions_df["competition_type"].value_counts()
            patterns["competition_distribution"] = {
                comp_type: count / total_transitions
                for comp_type, count in competition_dist.items()
            }

        return patterns

    def _calculate_success_story_metrics(self, transitions_df: pd.DataFrame) -> dict[str, Any]:
        """Identify high-impact transitions for success stories.

        Args:
            transitions_df: DataFrame with transition detections

        Returns:
            Dictionary with success story metrics
        """
        if transitions_df is None or len(transitions_df) == 0:
            return {"error": "No transitions available"}

        # Calculate success story score based on multiple factors
        success_scores = []

        for _idx, row in transitions_df.iterrows():
            score = 0.0
            factors = 0

            # Confidence factor (40% weight)
            confidence_cols = ["confidence", "likelihood_score", "score"]
            for col in confidence_cols:
                if col in row.index and pd.notna(row[col]):
                    conf_val = float(row[col])
                    score += 0.4 * conf_val
                    factors += 1
                    break

            # Signal strength factor (30% weight)
            signal_cols = ["agency_score", "competition_score", "patent_score", "cet_score"]
            signal_sum = 0
            signal_count: int = 0
            for col in signal_cols:
                if col in row.index and pd.notna(row[col]):
                    signal_sum += float(row[col])
                    signal_count += 1

            if signal_count > 0:
                avg_signal = signal_sum / signal_count
                score += 0.3 * avg_signal
                factors += 1

            # Timing factor (20% weight) - prefer closer transitions
            timing_cols = ["timing_score"]
            for col in timing_cols:
                if col in row.index and pd.notna(row[col]):
                    timing_val = float(row[col])
                    score += 0.2 * timing_val
                    factors += 1
                    break

            # Evidence factor (10% weight) - bonus for strong evidence
            evidence_cols = ["patent_count", "evidence_strength"]
            for col in evidence_cols:
                if col in row.index and pd.notna(row[col]):
                    evidence_val = min(1.0, float(row[col]) / 5.0)  # Normalize
                    score += 0.1 * evidence_val
                    factors += 1
                    break

            if factors > 0:
                score = score / factors  # Normalize by available factors

            success_scores.append(score)

        success_series = pd.Series(success_scores)

        # Identify high-impact transitions
        high_impact_threshold = self.thresholds["min_success_story_score"]
        high_impact_count = (success_series >= high_impact_threshold).sum()

        return {
            "total_transitions": len(transitions_df),
            "high_impact_transitions": int(high_impact_count),
            "high_impact_rate": high_impact_count / len(transitions_df),
            "average_success_score": float(success_series.mean()),
            "median_success_score": float(success_series.median()),
            "success_score_std": float(success_series.std()),
            "success_story_threshold": high_impact_threshold,
        }

    def _calculate_signal_strength_metrics(self, transitions_df: pd.DataFrame) -> dict[str, Any]:
        """Calculate overall signal strength metrics.

        Args:
            transitions_df: DataFrame with transition detections

        Returns:
            Dictionary with signal strength metrics
        """
        if transitions_df is None or len(transitions_df) == 0:
            return {"error": "No transitions available"}

        # Aggregate signal strengths
        signal_columns = [
            "agency_score",
            "timing_score",
            "competition_score",
            "patent_score",
            "cet_score",
        ]
        signal_strengths = []

        for _idx, row in transitions_df.iterrows():
            row_signals = []
            for col in signal_columns:
                if col in row.index and pd.notna(row[col]):
                    row_signals.append(float(row[col]))

            if row_signals:
                # Average signal strength for this transition
                avg_signal = sum(row_signals) / len(row_signals)
                signal_strengths.append(avg_signal)

        if not signal_strengths:
            return {"error": "No signal data available"}

        signal_series = pd.Series(signal_strengths)

        return {
            "average_signal_strength": float(signal_series.mean()),
            "median_signal_strength": float(signal_series.median()),
            "signal_strength_std": float(signal_series.std()),
            "strong_signals_rate": (signal_series >= 0.8).mean(),
            "weak_signals_rate": (signal_series < 0.4).mean(),
            "signal_coverage": len(signal_strengths) / len(transitions_df),
        }

    def _calculate_timing_analysis(self, transitions_df: pd.DataFrame) -> dict[str, Any]:
        """Analyze timing patterns in transitions.

        Args:
            transitions_df: DataFrame with transition detections

        Returns:
            Dictionary with timing analysis metrics
        """
        if transitions_df is None or len(transitions_df) == 0:
            return {"error": "No transitions available"}

        timing_analysis = {}

        # Analyze days/months between award and contract
        timing_columns = ["days_between_award_and_contract", "months_between_award_and_contract"]

        for col in timing_columns:
            if col in transitions_df.columns:
                values = pd.to_numeric(transitions_df[col], errors="coerce").dropna()
                if not values.empty:
                    timing_analysis[f"{col}_stats"] = {
                        "mean": float(values.mean()),
                        "median": float(values.median()),
                        "std": float(values.std()),
                        "min": float(values.min()),
                        "max": float(values.max()),
                        "quartiles": {
                            "25th": float(values.quantile(0.25)),
                            "75th": float(values.quantile(0.75)),
                        },
                    }

        # Analyze timing score distribution
        if "timing_score" in transitions_df.columns:
            timing_scores = transitions_df["timing_score"].dropna()
            timing_analysis["timing_score_distribution"] = {
                "mean": float(timing_scores.mean()),
                "high_timing_rate": (timing_scores >= 0.8).mean(),
                "low_timing_rate": (timing_scores < 0.4).mean(),
            }

        return timing_analysis

    def _calculate_data_hygiene(
        self, transitions_df: pd.DataFrame, awards_df: pd.DataFrame
    ) -> DataHygieneMetrics:
        """Calculate data hygiene metrics for transition detection data.

        Args:
            transitions_df: DataFrame with transition detections
            awards_df: DataFrame with original awards

        Returns:
            DataHygieneMetrics instance
        """
        total_records = len(transitions_df)

        # Calculate quality scores based on completeness and signal strength
        quality_scores = []
        for _idx, row in transitions_df.iterrows():
            score = 0.0

            # Award ID completeness (required)
            has_award_id = False
            award_id_cols = ["award_id", "award", "id"]
            for col in award_id_cols:
                if col in row.index and pd.notna(row[col]):
                    has_award_id = True
                    break
            score += 0.3 if has_award_id else 0.0

            # Confidence score availability
            confidence_cols = ["confidence", "likelihood_score", "score"]
            for col in confidence_cols:
                if col in row.index and pd.notna(row[col]):
                    conf_val = float(row[col])
                    score += 0.3 * conf_val  # Weight by confidence value
                    break

            # Signal completeness (at least one strong signal)
            signal_cols = ["agency_score", "timing_score", "competition_score"]
            has_signals = any(col in row.index and pd.notna(row[col]) for col in signal_cols)
            score += 0.2 if has_signals else 0.0

            # Evidence availability
            evidence_cols = ["patent_count", "evidence_bundle"]
            has_evidence = any(col in row.index and pd.notna(row[col]) for col in evidence_cols)
            score += 0.2 if has_evidence else 0.0

            quality_scores.append(min(1.0, score))

        quality_series = pd.Series(quality_scores)

        # Define clean vs dirty (quality score >= 0.7 is clean)
        clean_records = (quality_series >= 0.7).sum()
        dirty_records = total_records - clean_records

        return DataHygieneMetrics(
            total_records=total_records,
            clean_records=int(clean_records),
            dirty_records=int(dirty_records),
            clean_percentage=float(clean_records / total_records * 100)
            if total_records > 0
            else 0.0,
            quality_score_mean=float(quality_series.mean()),
            quality_score_median=float(quality_series.median()),
            quality_score_std=float(quality_series.std()),
            quality_score_min=float(quality_series.min()),
            quality_score_max=float(quality_series.max()),
            validation_pass_rate=float(clean_records / total_records) if total_records > 0 else 0.0,
            validation_errors=int(dirty_records),
            validation_warnings=0,
        )

    def _calculate_changes_summary(
        self, transitions_df: pd.DataFrame, awards_df: pd.DataFrame
    ) -> ChangesSummary:
        """Calculate summary of changes made during transition detection.

        Args:
            transitions_df: DataFrame with transition detections
            awards_df: DataFrame with original awards

        Returns:
            ChangesSummary instance
        """
        total_awards = len(awards_df) if awards_df is not None else 0
        total_transitions = len(transitions_df)

        # Fields added during detection
        detection_fields = [
            "transition_id",
            "likelihood_score",
            "confidence",
            "signals",
            "evidence",
            "primary_contract",
            "detected_at",
        ]

        fields_added = [field for field in detection_fields if field in transitions_df.columns]

        return ChangesSummary(
            total_records=total_awards,
            records_modified=total_transitions,
            records_unchanged=total_awards - total_transitions,
            modification_rate=total_transitions / total_awards if total_awards > 0 else 0.0,
            fields_added=fields_added,
            fields_modified=[],
            enrichment_sources={"transition_detection": total_transitions},
        )

    def _create_empty_report(self, run_context: dict[str, Any]) -> ModuleReport:
        """Create an empty report when no data is available.

        Args:
            run_context: Pipeline run context

        Returns:
            Empty ModuleReport
        """
        return self.create_module_report(
            run_id=run_context.get("run_id", "unknown"),
            stage="detect",
            total_records=0,
            records_processed=0,
            records_failed=0,
            duration_seconds=0.0,
            module_metrics={"error": "No transitions DataFrame available"},
        )
