"""SBIR enrichment analyzer for statistical reporting.

This analyzer focuses on SBIR enrichment operations, calculating match rates
by enrichment source, coverage metrics for enriched fields, and before/after
comparisons of data completeness.
"""

from typing import Any

import pandas as pd
from loguru import logger

from src.models.quality import ChangesSummary, DataHygieneMetrics, ModuleReport
from src.utils.reporting.analyzers.base_analyzer import AnalysisInsight, ModuleAnalyzer


class SbirEnrichmentAnalyzer(ModuleAnalyzer):
    """Analyzer for SBIR enrichment operations and data quality."""

    def __init__(self, config: dict[str, Any] | None = None):
        """Initialize SBIR enrichment analyzer.
        
        Args:
            config: Optional configuration for analysis thresholds
        """
        super().__init__("sbir_enrichment", config)

        # Default thresholds - can be overridden by config
        self.thresholds = {
            "min_match_rate": self.config.get("min_match_rate", 0.85),
            "min_high_confidence_rate": self.config.get("min_high_confidence_rate", 0.70),
            "min_coverage_rate": self.config.get("min_coverage_rate", 0.90),
            "max_fallback_rate": self.config.get("max_fallback_rate", 0.20),
        }

        # Key enrichment fields to analyze
        self.enrichment_fields = [
            "naics_code", "recipient_name", "recipient_uei", "recipient_duns",
            "sam_gov_data", "usaspending_data", "company_info"
        ]

        # Enrichment sources to track
        self.enrichment_sources = [
            "original_data", "usaspending_api", "sam_gov_api", "fuzzy_match",
            "agency_default", "sector_fallback"
        ]

    def analyze(self, module_data: dict[str, Any]) -> ModuleReport:
        """Analyze SBIR enrichment data and generate comprehensive report.
        
        Args:
            module_data: Dictionary containing:
                - enriched_df: Enriched SBIR DataFrame
                - original_df: Original SBIR DataFrame (for comparison)
                - enrichment_metrics: Enrichment operation metrics
                - run_context: Pipeline run context
                
        Returns:
            ModuleReport with SBIR enrichment analysis
        """
        logger.info("Starting SBIR enrichment analysis")

        enriched_df = module_data.get("enriched_df")
        original_df = module_data.get("original_df")
        enrichment_metrics = module_data.get("enrichment_metrics", {})
        run_context = module_data.get("run_context", {})

        if enriched_df is None:
            logger.warning("No enriched DataFrame provided for SBIR analysis")
            return self._create_empty_report(run_context)

        # Calculate key metrics
        key_metrics = self.get_key_metrics(module_data)

        # Generate insights
        insights = self.generate_insights(module_data)

        # Calculate data hygiene metrics
        data_hygiene = self._calculate_data_hygiene(enriched_df, original_df)

        # Calculate changes summary
        changes_summary = self._calculate_changes_summary(enriched_df, original_df)

        # Extract processing metrics
        total_records = len(enriched_df) if enriched_df is not None else 0
        records_processed = enrichment_metrics.get("records_processed", total_records)
        records_failed = enrichment_metrics.get("records_failed", 0)
        duration_seconds = enrichment_metrics.get("duration_seconds", 0.0)

        # Create module report
        report = self.create_module_report(
            run_id=run_context.get("run_id", "unknown"),
            stage="enrich",
            total_records=total_records,
            records_processed=records_processed,
            records_failed=records_failed,
            duration_seconds=duration_seconds,
            module_metrics=key_metrics,
            data_hygiene=data_hygiene,
            changes_summary=changes_summary,
        )

        logger.info(f"SBIR enrichment analysis complete: {len(insights)} insights generated")
        return report

    def get_key_metrics(self, module_data: dict[str, Any]) -> dict[str, Any]:
        """Extract key metrics from SBIR enrichment data.
        
        Args:
            module_data: Module data containing enriched DataFrame
            
        Returns:
            Dictionary of key SBIR enrichment metrics
        """
        enriched_df = module_data.get("enriched_df")
        original_df = module_data.get("original_df")
        enrichment_metrics = module_data.get("enrichment_metrics", {})

        if enriched_df is None:
            return {"error": "No enriched DataFrame available"}

        total_records = len(enriched_df)

        # Calculate match rates by source
        match_rates = self._calculate_match_rates_by_source(enriched_df)

        # Calculate field coverage metrics
        coverage_metrics = self._calculate_field_coverage(enriched_df, original_df)

        # Calculate confidence distribution
        confidence_distribution = self._calculate_confidence_distribution(enriched_df)

        # Calculate enrichment success metrics
        enrichment_success = self._calculate_enrichment_success(enriched_df)

        # Calculate before/after completeness comparison
        completeness_comparison = self._calculate_completeness_comparison(enriched_df, original_df)

        return {
            "total_records": total_records,
            "match_rates_by_source": match_rates,
            "field_coverage_metrics": coverage_metrics,
            "confidence_distribution": confidence_distribution,
            "enrichment_success_metrics": enrichment_success,
            "completeness_comparison": completeness_comparison,
            "overall_match_rate": enrichment_metrics.get("overall_match_rate", 0.0),
            "processing_duration_seconds": enrichment_metrics.get("duration_seconds", 0.0),
            "records_per_second": enrichment_metrics.get("records_per_second", 0.0),
        }

    def generate_insights(self, module_data: dict[str, Any]) -> list[AnalysisInsight]:
        """Generate automated insights for SBIR enrichment analysis.
        
        Args:
            module_data: Module data containing enriched DataFrame
            
        Returns:
            List of analysis insights and recommendations
        """
        insights = []
        enriched_df = module_data.get("enriched_df")
        enrichment_metrics = module_data.get("enrichment_metrics", {})

        if enriched_df is None:
            return insights

        # Analyze overall match rate
        overall_match_rate = enrichment_metrics.get("overall_match_rate", 0.0)
        if overall_match_rate < self.thresholds["min_match_rate"]:
            insights.append(AnalysisInsight(
                category="enrichment_quality",
                title="Low Overall Match Rate",
                message=f"Overall match rate ({overall_match_rate:.1%}) is below threshold ({self.thresholds['min_match_rate']:.1%})",
                severity="warning",
                confidence=0.9,
                affected_records=int(len(enriched_df) * (1 - overall_match_rate)),
                recommendations=[
                    "Review enrichment source configurations",
                    "Check data quality of input records",
                    "Consider adjusting fuzzy matching thresholds",
                    "Validate API connectivity and rate limits"
                ],
                metadata={"current_rate": overall_match_rate, "threshold": self.thresholds["min_match_rate"]}
            ))

        # Analyze confidence distribution
        confidence_dist = self._calculate_confidence_distribution(enriched_df)
        high_confidence_rate = confidence_dist.get("high_confidence_rate", 0.0)
        if high_confidence_rate < self.thresholds["min_high_confidence_rate"]:
            insights.append(AnalysisInsight(
                category="enrichment_confidence",
                title="Low High-Confidence Enrichment Rate",
                message=f"High-confidence enrichment rate ({high_confidence_rate:.1%}) is below target ({self.thresholds['min_high_confidence_rate']:.1%})",
                severity="info",
                confidence=0.8,
                affected_records=int(len(enriched_df) * (1 - high_confidence_rate)),
                recommendations=[
                    "Prioritize exact match sources over fuzzy matching",
                    "Improve data standardization before enrichment",
                    "Review and update agency default mappings",
                    "Consider additional high-quality data sources"
                ],
                metadata={"current_rate": high_confidence_rate, "threshold": self.thresholds["min_high_confidence_rate"]}
            ))

        # Analyze fallback usage
        match_rates = self._calculate_match_rates_by_source(enriched_df)
        fallback_rate = match_rates.get("sector_fallback", 0.0) + match_rates.get("agency_default", 0.0)
        if fallback_rate > self.thresholds["max_fallback_rate"]:
            insights.append(AnalysisInsight(
                category="enrichment_fallback",
                title="High Fallback Usage",
                message=f"Fallback enrichment rate ({fallback_rate:.1%}) exceeds threshold ({self.thresholds['max_fallback_rate']:.1%})",
                severity="warning",
                confidence=0.85,
                affected_records=int(len(enriched_df) * fallback_rate),
                recommendations=[
                    "Investigate primary enrichment source failures",
                    "Improve data quality of input records",
                    "Review and update enrichment source priorities",
                    "Consider adding additional enrichment sources"
                ],
                metadata={"current_rate": fallback_rate, "threshold": self.thresholds["max_fallback_rate"]}
            ))

        # Analyze field-specific coverage
        coverage_metrics = self._calculate_field_coverage(enriched_df, module_data.get("original_df"))
        for field, coverage in coverage_metrics.items():
            if coverage < self.thresholds["min_coverage_rate"]:
                insights.append(AnalysisInsight(
                    category="field_coverage",
                    title=f"Low Coverage for {field}",
                    message=f"Field '{field}' coverage ({coverage:.1%}) is below target ({self.thresholds['min_coverage_rate']:.1%})",
                    severity="info",
                    confidence=0.7,
                    affected_records=int(len(enriched_df) * (1 - coverage)),
                    recommendations=[
                        f"Review enrichment sources for {field}",
                        f"Check data quality requirements for {field}",
                        f"Consider alternative sources for {field} data"
                    ],
                    metadata={"field": field, "current_coverage": coverage, "threshold": self.thresholds["min_coverage_rate"]}
                ))

        return insights

    def _calculate_match_rates_by_source(self, enriched_df: pd.DataFrame) -> dict[str, float]:
        """Calculate match rates by enrichment source.
        
        Args:
            enriched_df: Enriched SBIR DataFrame
            
        Returns:
            Dictionary mapping source names to match rates
        """
        total_records = len(enriched_df)
        if total_records == 0:
            return {}

        match_rates = {}

        # Check for enrichment source columns
        source_columns = [
            "_usaspending_match_method", "_sam_gov_match_method", "_fuzzy_match_method",
            "enrichment_source", "match_source", "naics_source"
        ]

        for col in source_columns:
            if col in enriched_df.columns:
                source_counts = enriched_df[col].value_counts()
                for source, count in source_counts.items():
                    if pd.notna(source):
                        source_name = str(source).lower()
                        match_rates[source_name] = count / total_records

        # If no specific source columns, estimate from enrichment patterns
        if not match_rates:
            # Count records with enriched data vs original
            for field in self.enrichment_fields:
                if field in enriched_df.columns:
                    enriched_count = enriched_df[field].notna().sum()
                    match_rates[f"{field}_enriched"] = enriched_count / total_records

        return match_rates

    def _calculate_field_coverage(self, enriched_df: pd.DataFrame, original_df: pd.DataFrame | None) -> dict[str, float]:
        """Calculate coverage metrics for each enriched field.
        
        Args:
            enriched_df: Enriched SBIR DataFrame
            original_df: Original SBIR DataFrame for comparison
            
        Returns:
            Dictionary mapping field names to coverage rates
        """
        total_records = len(enriched_df)
        if total_records == 0:
            return {}

        coverage_metrics = {}

        for field in self.enrichment_fields:
            if field in enriched_df.columns:
                # Calculate coverage as non-null values
                enriched_count = enriched_df[field].notna().sum()
                coverage_rate = enriched_count / total_records
                coverage_metrics[field] = coverage_rate

                # If original data available, calculate improvement
                if original_df is not None and field in original_df.columns:
                    original_count = original_df[field].notna().sum()
                    original_rate = original_count / len(original_df) if len(original_df) > 0 else 0
                    improvement = coverage_rate - original_rate
                    coverage_metrics[f"{field}_improvement"] = improvement

        return coverage_metrics

    def _calculate_confidence_distribution(self, enriched_df: pd.DataFrame) -> dict[str, Any]:
        """Calculate confidence score distribution.
        
        Args:
            enriched_df: Enriched SBIR DataFrame
            
        Returns:
            Dictionary with confidence distribution metrics
        """
        confidence_columns = [
            "enrichment_confidence", "match_confidence", "confidence_score",
            "_usaspending_confidence", "_sam_gov_confidence"
        ]

        confidence_values = []
        for col in confidence_columns:
            if col in enriched_df.columns:
                values = enriched_df[col].dropna()
                confidence_values.extend(values.tolist())

        if not confidence_values:
            return {"error": "No confidence scores found"}

        confidence_series = pd.Series(confidence_values)

        # Categorize confidence levels
        high_confidence = (confidence_series >= 0.8).sum()
        medium_confidence = ((confidence_series >= 0.6) & (confidence_series < 0.8)).sum()
        low_confidence = (confidence_series < 0.6).sum()
        total_with_confidence = len(confidence_series)

        return {
            "total_records_with_confidence": total_with_confidence,
            "high_confidence_count": int(high_confidence),
            "medium_confidence_count": int(medium_confidence),
            "low_confidence_count": int(low_confidence),
            "high_confidence_rate": high_confidence / total_with_confidence if total_with_confidence > 0 else 0,
            "medium_confidence_rate": medium_confidence / total_with_confidence if total_with_confidence > 0 else 0,
            "low_confidence_rate": low_confidence / total_with_confidence if total_with_confidence > 0 else 0,
            "average_confidence": float(confidence_series.mean()),
            "median_confidence": float(confidence_series.median()),
            "min_confidence": float(confidence_series.min()),
            "max_confidence": float(confidence_series.max()),
        }

    def _calculate_enrichment_success(self, enriched_df: pd.DataFrame) -> dict[str, Any]:
        """Calculate overall enrichment success metrics.
        
        Args:
            enriched_df: Enriched SBIR DataFrame
            
        Returns:
            Dictionary with enrichment success metrics
        """
        total_records = len(enriched_df)
        if total_records == 0:
            return {}

        # Count records with any enrichment
        enriched_records = 0
        for field in self.enrichment_fields:
            if field in enriched_df.columns:
                field_enriched = enriched_df[field].notna().sum()
                enriched_records = max(enriched_records, field_enriched)

        # Count records with multiple enrichments
        multi_enriched = 0
        for idx, row in enriched_df.iterrows():
            enriched_fields = sum(1 for field in self.enrichment_fields
                                if field in row.index and pd.notna(row[field]))
            if enriched_fields > 1:
                multi_enriched += 1

        return {
            "total_records": total_records,
            "enriched_records": enriched_records,
            "unenriched_records": total_records - enriched_records,
            "enrichment_rate": enriched_records / total_records,
            "multi_enriched_records": multi_enriched,
            "multi_enrichment_rate": multi_enriched / total_records,
        }

    def _calculate_completeness_comparison(self, enriched_df: pd.DataFrame, original_df: pd.DataFrame | None) -> dict[str, Any]:
        """Calculate before/after completeness comparison.
        
        Args:
            enriched_df: Enriched SBIR DataFrame
            original_df: Original SBIR DataFrame
            
        Returns:
            Dictionary with completeness comparison metrics
        """
        if original_df is None:
            return {"error": "No original DataFrame for comparison"}

        comparison = {}

        # Calculate overall completeness
        enriched_completeness = enriched_df.notna().sum().sum() / (len(enriched_df) * len(enriched_df.columns))
        original_completeness = original_df.notna().sum().sum() / (len(original_df) * len(original_df.columns))

        comparison["overall"] = {
            "original_completeness": original_completeness,
            "enriched_completeness": enriched_completeness,
            "improvement": enriched_completeness - original_completeness,
        }

        # Calculate field-by-field completeness for common fields
        common_fields = set(enriched_df.columns) & set(original_df.columns)
        comparison["by_field"] = {}

        for field in common_fields:
            original_complete = original_df[field].notna().sum() / len(original_df)
            enriched_complete = enriched_df[field].notna().sum() / len(enriched_df)

            comparison["by_field"][field] = {
                "original_completeness": original_complete,
                "enriched_completeness": enriched_complete,
                "improvement": enriched_complete - original_complete,
            }

        return comparison

    def _calculate_data_hygiene(self, enriched_df: pd.DataFrame, original_df: pd.DataFrame | None) -> DataHygieneMetrics:
        """Calculate data hygiene metrics for enriched data.
        
        Args:
            enriched_df: Enriched SBIR DataFrame
            original_df: Original SBIR DataFrame
            
        Returns:
            DataHygieneMetrics instance
        """
        total_records = len(enriched_df)

        # Calculate quality scores (simplified)
        quality_scores = []
        for idx, row in enriched_df.iterrows():
            # Simple quality score based on completeness and enrichment
            non_null_count = row.notna().sum()
            total_fields = len(row)
            completeness_score = non_null_count / total_fields

            # Bonus for enrichment
            enrichment_bonus = 0.0
            for field in self.enrichment_fields:
                if field in row.index and pd.notna(row[field]):
                    enrichment_bonus += 0.1

            quality_score = min(1.0, completeness_score + enrichment_bonus)
            quality_scores.append(quality_score)

        quality_series = pd.Series(quality_scores)

        # Define clean vs dirty (quality score >= 0.8 is clean)
        clean_records = (quality_series >= 0.8).sum()
        dirty_records = total_records - clean_records

        return DataHygieneMetrics(
            total_records=total_records,
            clean_records=int(clean_records),
            dirty_records=int(dirty_records),
            clean_percentage=float(clean_records / total_records * 100) if total_records > 0 else 0.0,
            quality_score_mean=float(quality_series.mean()),
            quality_score_median=float(quality_series.median()),
            quality_score_std=float(quality_series.std()),
            quality_score_min=float(quality_series.min()),
            quality_score_max=float(quality_series.max()),
            validation_pass_rate=float(clean_records / total_records) if total_records > 0 else 0.0,
            validation_errors=int(dirty_records),
            validation_warnings=0,  # Would need specific validation logic
        )

    def _calculate_changes_summary(self, enriched_df: pd.DataFrame, original_df: pd.DataFrame | None) -> ChangesSummary | None:
        """Calculate summary of changes made during enrichment.
        
        Args:
            enriched_df: Enriched SBIR DataFrame
            original_df: Original SBIR DataFrame
            
        Returns:
            ChangesSummary instance or None if no original data
        """
        if original_df is None:
            return None

        total_records = len(enriched_df)

        # Find added fields
        original_fields = set(original_df.columns)
        enriched_fields = set(enriched_df.columns)
        fields_added = list(enriched_fields - original_fields)

        # Count modified records (simplified - records with new non-null values)
        records_modified = 0
        for field in fields_added:
            if field in enriched_df.columns:
                records_modified += enriched_df[field].notna().sum()

        # Remove duplicates (record modified if any field was enriched)
        records_modified = min(records_modified, total_records)
        records_unchanged = total_records - records_modified

        # Count enrichment sources
        enrichment_sources = {}
        for source in self.enrichment_sources:
            # This would need to be extracted from actual enrichment metadata
            enrichment_sources[source] = 0

        return ChangesSummary(
            total_records=total_records,
            records_modified=records_modified,
            records_unchanged=records_unchanged,
            modification_rate=records_modified / total_records if total_records > 0 else 0.0,
            fields_added=fields_added,
            fields_modified=[],  # Would need field-by-field comparison
            enrichment_sources=enrichment_sources,
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
            stage="enrich",
            total_records=0,
            records_processed=0,
            records_failed=0,
            duration_seconds=0.0,
            module_metrics={"error": "No enriched DataFrame available"},
        )
