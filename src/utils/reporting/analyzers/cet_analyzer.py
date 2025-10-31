"""CET classification analyzer for statistical reporting.

This analyzer focuses on Critical and Emerging Technologies (CET) classification
operations, generating technology category distribution statistics, calculating
classification confidence score distributions, and analyzing coverage metrics
across CET taxonomy areas.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
from loguru import logger

from src.models.quality import ChangesSummary, DataHygieneMetrics, ModuleReport
from src.utils.reporting.analyzers.base_analyzer import AnalysisInsight, ModuleAnalyzer


class CetClassificationAnalyzer(ModuleAnalyzer):
    """Analyzer for CET classification operations and taxonomy coverage."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize CET classification analyzer.
        
        Args:
            config: Optional configuration for analysis thresholds
        """
        super().__init__("cet_classification", config)
        
        # Default thresholds - can be overridden by config
        self.thresholds = {
            "min_classification_rate": self.config.get("min_classification_rate", 0.90),
            "min_high_confidence_rate": self.config.get("min_high_confidence_rate", 0.60),
            "min_taxonomy_coverage": self.config.get("min_taxonomy_coverage", 0.70),
            "max_unclassified_rate": self.config.get("max_unclassified_rate", 0.15),
        }
        
        # CET taxonomy areas (major categories)
        self.cet_areas = [
            "artificial_intelligence", "quantum_information_technologies", 
            "biotechnology", "advanced_materials", "advanced_manufacturing",
            "microelectronics", "space_technology", "renewable_energy",
            "advanced_computing", "hypersonics", "networked_sensors",
            "data_science", "autonomous_systems", "human_machine_interfaces",
            "directed_energy", "financial_technologies", "semiconductors",
            "advanced_nuclear", "cybersecurity"
        ]
        
        # Classification confidence bands
        self.confidence_bands = {
            "high": (70, 100),
            "medium": (40, 69),
            "low": (0, 39)
        }
    
    def analyze(self, module_data: Dict[str, Any]) -> ModuleReport:
        """Analyze CET classification data and generate comprehensive report.
        
        Args:
            module_data: Dictionary containing:
                - classified_df: CET classified DataFrame
                - classification_results: Classification operation results
                - taxonomy_data: CET taxonomy information
                - run_context: Pipeline run context
                
        Returns:
            ModuleReport with CET classification analysis
        """
        logger.info("Starting CET classification analysis")
        
        classified_df = module_data.get("classified_df")
        classification_results = module_data.get("classification_results", {})
        taxonomy_data = module_data.get("taxonomy_data", {})
        run_context = module_data.get("run_context", {})
        
        if classified_df is None:
            logger.warning("No classified DataFrame provided for CET analysis")
            return self._create_empty_report(run_context)
        
        # Calculate key metrics
        key_metrics = self.get_key_metrics(module_data)
        
        # Generate insights
        insights = self.generate_insights(module_data)
        
        # Calculate data hygiene metrics
        data_hygiene = self._calculate_data_hygiene(classified_df, classification_results)
        
        # Calculate changes summary
        changes_summary = self._calculate_changes_summary(classified_df, classification_results)
        
        # Extract processing metrics
        total_records = len(classified_df) if classified_df is not None else 0
        records_processed = classification_results.get("classified_records", total_records)
        records_failed = classification_results.get("failed_records", 0)
        duration_seconds = classification_results.get("duration_seconds", 0.0)
        
        # Create module report
        report = self.create_module_report(
            run_id=run_context.get("run_id", "unknown"),
            stage="transform",
            total_records=total_records,
            records_processed=records_processed,
            records_failed=records_failed,
            duration_seconds=duration_seconds,
            module_metrics=key_metrics,
            data_hygiene=data_hygiene,
            changes_summary=changes_summary,
        )
        
        logger.info(f"CET classification analysis complete: {len(insights)} insights generated")
        return report
    
    def get_key_metrics(self, module_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract key metrics from CET classification data.
        
        Args:
            module_data: Module data containing classified DataFrame
            
        Returns:
            Dictionary of key CET classification metrics
        """
        classified_df = module_data.get("classified_df")
        classification_results = module_data.get("classification_results", {})
        taxonomy_data = module_data.get("taxonomy_data", {})
        
        if classified_df is None:
            return {"error": "No classified DataFrame available"}
        
        total_records = len(classified_df)
        
        # Calculate technology category distribution
        category_distribution = self._calculate_category_distribution(classified_df)
        
        # Calculate confidence score distribution
        confidence_distribution = self._calculate_confidence_distribution(classified_df)
        
        # Calculate taxonomy coverage metrics
        taxonomy_coverage = self._calculate_taxonomy_coverage(classified_df, taxonomy_data)
        
        # Calculate classification success metrics
        classification_success = self._calculate_classification_success(classified_df, classification_results)
        
        # Calculate supporting evidence metrics
        evidence_metrics = self._calculate_evidence_metrics(classified_df)
        
        return {
            "total_records": total_records,
            "category_distribution": category_distribution,
            "confidence_distribution": confidence_distribution,
            "taxonomy_coverage": taxonomy_coverage,
            "classification_success": classification_success,
            "evidence_metrics": evidence_metrics,
            "processing_duration_seconds": classification_results.get("duration_seconds", 0.0),
            "classification_throughput": classification_results.get("records_per_second", 0.0),
        }
    
    def generate_insights(self, module_data: Dict[str, Any]) -> List[AnalysisInsight]:
        """Generate automated insights for CET classification analysis.
        
        Args:
            module_data: Module data containing classified DataFrame
            
        Returns:
            List of analysis insights and recommendations
        """
        insights = []
        classified_df = module_data.get("classified_df")
        classification_results = module_data.get("classification_results", {})
        
        if classified_df is None:
            return insights
        
        # Analyze overall classification rate
        classification_rate = classification_results.get("classification_rate", 0.0)
        if classification_rate < self.thresholds["min_classification_rate"]:
            insights.append(AnalysisInsight(
                category="classification_coverage",
                title="Low CET Classification Rate",
                message=f"CET classification rate ({classification_rate:.1%}) is below threshold ({self.thresholds['min_classification_rate']:.1%})",
                severity="warning",
                confidence=0.9,
                affected_records=int(len(classified_df) * (1 - classification_rate)),
                recommendations=[
                    "Review classification model performance",
                    "Check input data quality for classification",
                    "Consider retraining with additional data",
                    "Validate taxonomy mapping completeness"
                ],
                metadata={"current_rate": classification_rate, "threshold": self.thresholds["min_classification_rate"]}
            ))
        
        # Analyze confidence distribution
        confidence_dist = self._calculate_confidence_distribution(classified_df)
        high_confidence_rate = confidence_dist.get("high_confidence_rate", 0.0)
        if high_confidence_rate < self.thresholds["min_high_confidence_rate"]:
            insights.append(AnalysisInsight(
                category="classification_confidence",
                title="Low High-Confidence Classification Rate",
                message=f"High-confidence classification rate ({high_confidence_rate:.1%}) is below target ({self.thresholds['min_high_confidence_rate']:.1%})",
                severity="info",
                confidence=0.8,
                affected_records=int(len(classified_df) * (1 - high_confidence_rate)),
                recommendations=[
                    "Review classification model confidence calibration",
                    "Consider ensemble methods for improved confidence",
                    "Validate training data quality and diversity",
                    "Implement active learning for uncertain cases"
                ],
                metadata={"current_rate": high_confidence_rate, "threshold": self.thresholds["min_high_confidence_rate"]}
            ))
        
        # Analyze taxonomy coverage
        taxonomy_coverage = self._calculate_taxonomy_coverage(classified_df, module_data.get("taxonomy_data", {}))
        coverage_rate = taxonomy_coverage.get("coverage_rate", 0.0)
        if coverage_rate < self.thresholds["min_taxonomy_coverage"]:
            insights.append(AnalysisInsight(
                category="taxonomy_coverage",
                title="Low CET Taxonomy Coverage",
                message=f"CET taxonomy coverage ({coverage_rate:.1%}) is below target ({self.thresholds['min_taxonomy_coverage']:.1%})",
                severity="info",
                confidence=0.7,
                affected_records=len(classified_df),
                recommendations=[
                    "Review data diversity across technology areas",
                    "Consider targeted data collection for underrepresented areas",
                    "Validate taxonomy completeness and relevance",
                    "Implement balanced sampling strategies"
                ],
                metadata={"current_coverage": coverage_rate, "threshold": self.thresholds["min_taxonomy_coverage"]}
            ))
        
        # Analyze unclassified rate
        unclassified_rate = classification_results.get("unclassified_rate", 0.0)
        if unclassified_rate > self.thresholds["max_unclassified_rate"]:
            insights.append(AnalysisInsight(
                category="unclassified_records",
                title="High Unclassified Record Rate",
                message=f"Unclassified record rate ({unclassified_rate:.1%}) exceeds threshold ({self.thresholds['max_unclassified_rate']:.1%})",
                severity="warning",
                confidence=0.85,
                affected_records=int(len(classified_df) * unclassified_rate),
                recommendations=[
                    "Investigate common patterns in unclassified records",
                    "Review classification threshold settings",
                    "Consider expanding taxonomy to cover edge cases",
                    "Implement fallback classification strategies"
                ],
                metadata={"current_rate": unclassified_rate, "threshold": self.thresholds["max_unclassified_rate"]}
            ))
        
        # Analyze category imbalance
        category_dist = self._calculate_category_distribution(classified_df)
        if category_dist:
            max_category_rate = max(category_dist.values())
            min_category_rate = min(category_dist.values())
            imbalance_ratio = max_category_rate / min_category_rate if min_category_rate > 0 else float('inf')
            
            if imbalance_ratio > 10:  # Significant imbalance
                insights.append(AnalysisInsight(
                    category="category_imbalance",
                    title="Significant CET Category Imbalance",
                    message=f"CET category distribution shows significant imbalance (ratio: {imbalance_ratio:.1f}:1)",
                    severity="info",
                    confidence=0.8,
                    affected_records=len(classified_df),
                    recommendations=[
                        "Review data collection strategies for balanced representation",
                        "Consider weighted sampling or augmentation techniques",
                        "Validate that imbalance reflects real-world distribution",
                        "Implement category-specific evaluation metrics"
                    ],
                    metadata={"imbalance_ratio": imbalance_ratio, "max_rate": max_category_rate, "min_rate": min_category_rate}
                ))
        
        return insights
    
    def _calculate_category_distribution(self, classified_df: pd.DataFrame) -> Dict[str, float]:
        """Calculate technology category distribution statistics.
        
        Args:
            classified_df: CET classified DataFrame
            
        Returns:
            Dictionary mapping CET categories to their distribution rates
        """
        total_records = len(classified_df)
        if total_records == 0:
            return {}
        
        category_distribution = {}
        
        # Check for CET classification columns
        cet_columns = [
            "primary_cet_area", "cet_classification", "technology_category",
            "cet_areas", "classified_categories"
        ]
        
        for col in cet_columns:
            if col in classified_df.columns:
                # Handle single category assignments
                if col in ["primary_cet_area", "cet_classification", "technology_category"]:
                    category_counts = classified_df[col].value_counts()
                    for category, count in category_counts.items():
                        if pd.notna(category):
                            category_name = str(category).lower()
                            category_distribution[category_name] = count / total_records
                
                # Handle multiple category assignments (JSON or list format)
                elif col in ["cet_areas", "classified_categories"]:
                    # This would need specific parsing based on data format
                    # For now, assume comma-separated values
                    for idx, value in classified_df[col].dropna().items():
                        if isinstance(value, str) and "," in value:
                            categories = [cat.strip().lower() for cat in value.split(",")]
                            for category in categories:
                                if category in self.cet_areas:
                                    category_distribution[category] = category_distribution.get(category, 0) + (1 / total_records)
        
        return category_distribution
    
    def _calculate_confidence_distribution(self, classified_df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate classification confidence score distributions.
        
        Args:
            classified_df: CET classified DataFrame
            
        Returns:
            Dictionary with confidence distribution metrics
        """
        confidence_columns = [
            "classification_confidence", "cet_confidence", "confidence_score",
            "primary_confidence", "classification_score"
        ]
        
        confidence_values = []
        for col in confidence_columns:
            if col in classified_df.columns:
                values = pd.to_numeric(classified_df[col], errors="coerce").dropna()
                confidence_values.extend(values.tolist())
        
        if not confidence_values:
            return {"error": "No confidence scores found"}
        
        confidence_series = pd.Series(confidence_values)
        
        # Categorize by confidence bands
        high_confidence = ((confidence_series >= self.confidence_bands["high"][0]) & 
                          (confidence_series <= self.confidence_bands["high"][1])).sum()
        medium_confidence = ((confidence_series >= self.confidence_bands["medium"][0]) & 
                            (confidence_series <= self.confidence_bands["medium"][1])).sum()
        low_confidence = ((confidence_series >= self.confidence_bands["low"][0]) & 
                         (confidence_series <= self.confidence_bands["low"][1])).sum()
        
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
            "confidence_std": float(confidence_series.std()),
            "min_confidence": float(confidence_series.min()),
            "max_confidence": float(confidence_series.max()),
            "confidence_bands": self.confidence_bands,
        }
    
    def _calculate_taxonomy_coverage(self, classified_df: pd.DataFrame, taxonomy_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze coverage metrics across CET taxonomy areas.
        
        Args:
            classified_df: CET classified DataFrame
            taxonomy_data: CET taxonomy information
            
        Returns:
            Dictionary with taxonomy coverage metrics
        """
        total_records = len(classified_df)
        
        # Get classified categories
        classified_categories = set()
        category_columns = ["primary_cet_area", "cet_classification", "technology_category"]
        
        for col in category_columns:
            if col in classified_df.columns:
                categories = classified_df[col].dropna().unique()
                classified_categories.update(str(cat).lower() for cat in categories)
        
        # Calculate coverage against known CET areas
        covered_areas = classified_categories.intersection(set(self.cet_areas))
        uncovered_areas = set(self.cet_areas) - covered_areas
        
        coverage_rate = len(covered_areas) / len(self.cet_areas) if self.cet_areas else 0
        
        # Calculate records per category
        records_per_category = {}
        for area in covered_areas:
            count = 0
            for col in category_columns:
                if col in classified_df.columns:
                    count += (classified_df[col].str.lower() == area).sum()
            records_per_category[area] = count
        
        return {
            "total_cet_areas": len(self.cet_areas),
            "covered_areas": list(covered_areas),
            "uncovered_areas": list(uncovered_areas),
            "coverage_rate": coverage_rate,
            "areas_covered_count": len(covered_areas),
            "areas_uncovered_count": len(uncovered_areas),
            "records_per_category": records_per_category,
            "average_records_per_area": sum(records_per_category.values()) / len(covered_areas) if covered_areas else 0,
            "taxonomy_utilization": len(classified_categories) / len(self.cet_areas) if self.cet_areas else 0,
        }
    
    def _calculate_classification_success(self, classified_df: pd.DataFrame, classification_results: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate overall classification success metrics.
        
        Args:
            classified_df: CET classified DataFrame
            classification_results: Classification operation results
            
        Returns:
            Dictionary with classification success metrics
        """
        total_records = len(classified_df)
        
        # Count classified vs unclassified records
        classified_count = 0
        unclassified_count = 0
        
        # Check for classification indicator columns
        classification_columns = [
            "primary_cet_area", "cet_classification", "technology_category", "is_classified"
        ]
        
        for col in classification_columns:
            if col in classified_df.columns:
                if col == "is_classified":
                    # Boolean indicator
                    classified_count = classified_df[col].sum() if classified_df[col].dtype == bool else 0
                else:
                    # Non-null values indicate classification
                    classified_count = max(classified_count, classified_df[col].notna().sum())
        
        unclassified_count = total_records - classified_count
        
        # Calculate success rates
        classification_rate = classified_count / total_records if total_records > 0 else 0
        unclassified_rate = unclassified_count / total_records if total_records > 0 else 0
        
        # Extract additional metrics from results
        processing_time = classification_results.get("duration_seconds", 0.0)
        throughput = classified_count / processing_time if processing_time > 0 else 0
        
        return {
            "total_records": total_records,
            "classified_records": classified_count,
            "unclassified_records": unclassified_count,
            "classification_rate": classification_rate,
            "unclassified_rate": unclassified_rate,
            "classification_throughput": throughput,
            "processing_duration_seconds": processing_time,
            "model_accuracy": classification_results.get("model_accuracy", 0.0),
            "model_precision": classification_results.get("model_precision", 0.0),
            "model_recall": classification_results.get("model_recall", 0.0),
            "model_f1_score": classification_results.get("model_f1_score", 0.0),
        }
    
    def _calculate_evidence_metrics(self, classified_df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate supporting evidence metrics for classifications.
        
        Args:
            classified_df: CET classified DataFrame
            
        Returns:
            Dictionary with evidence metrics
        """
        evidence_columns = [
            "classification_evidence", "supporting_evidence", "evidence_text",
            "keywords_matched", "classification_rationale"
        ]
        
        evidence_metrics = {}
        
        for col in evidence_columns:
            if col in classified_df.columns:
                # Count records with evidence
                with_evidence = classified_df[col].notna().sum()
                evidence_rate = with_evidence / len(classified_df) if len(classified_df) > 0 else 0
                
                evidence_metrics[f"{col}_coverage"] = evidence_rate
                evidence_metrics[f"{col}_count"] = int(with_evidence)
                
                # Analyze evidence length/quality if text-based
                if col in ["classification_evidence", "supporting_evidence", "evidence_text", "classification_rationale"]:
                    evidence_texts = classified_df[col].dropna()
                    if not evidence_texts.empty:
                        text_lengths = evidence_texts.str.len()
                        evidence_metrics[f"{col}_avg_length"] = float(text_lengths.mean())
                        evidence_metrics[f"{col}_median_length"] = float(text_lengths.median())
        
        # Overall evidence availability
        total_evidence_fields = len([col for col in evidence_columns if col in classified_df.columns])
        if total_evidence_fields > 0:
            # Records with any evidence
            has_any_evidence = classified_df[evidence_columns].notna().any(axis=1).sum()
            evidence_metrics["overall_evidence_rate"] = has_any_evidence / len(classified_df)
            evidence_metrics["records_with_evidence"] = int(has_any_evidence)
        
        return evidence_metrics
    
    def _calculate_data_hygiene(self, classified_df: pd.DataFrame, classification_results: Dict[str, Any]) -> DataHygieneMetrics:
        """Calculate data hygiene metrics for CET classified data.
        
        Args:
            classified_df: CET classified DataFrame
            classification_results: Classification results
            
        Returns:
            DataHygieneMetrics instance
        """
        total_records = len(classified_df)
        
        # Calculate quality scores based on classification completeness and confidence
        quality_scores = []
        for idx, row in classified_df.iterrows():
            # Base score from classification presence
            has_classification = False
            classification_columns = ["primary_cet_area", "cet_classification", "technology_category"]
            for col in classification_columns:
                if col in row.index and pd.notna(row[col]):
                    has_classification = True
                    break
            
            base_score = 0.7 if has_classification else 0.3
            
            # Bonus for confidence score
            confidence_bonus = 0.0
            confidence_columns = ["classification_confidence", "cet_confidence", "confidence_score"]
            for col in confidence_columns:
                if col in row.index and pd.notna(row[col]):
                    confidence = float(row[col])
                    if confidence >= 70:
                        confidence_bonus = 0.3
                    elif confidence >= 40:
                        confidence_bonus = 0.2
                    else:
                        confidence_bonus = 0.1
                    break
            
            # Bonus for evidence
            evidence_bonus = 0.0
            evidence_columns = ["classification_evidence", "supporting_evidence"]
            for col in evidence_columns:
                if col in row.index and pd.notna(row[col]):
                    evidence_bonus = 0.1
                    break
            
            quality_score = min(1.0, base_score + confidence_bonus + evidence_bonus)
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
            validation_warnings=0,
        )
    
    def _calculate_changes_summary(self, classified_df: pd.DataFrame, classification_results: Dict[str, Any]) -> ChangesSummary:
        """Calculate summary of changes made during CET classification.
        
        Args:
            classified_df: CET classified DataFrame
            classification_results: Classification results
            
        Returns:
            ChangesSummary instance
        """
        total_records = len(classified_df)
        
        # Fields added during classification
        classification_fields = [
            "primary_cet_area", "cet_classification", "technology_category",
            "classification_confidence", "cet_confidence", "confidence_score",
            "classification_evidence", "supporting_evidence", "classification_rationale"
        ]
        
        fields_added = [field for field in classification_fields if field in classified_df.columns]
        
        # Count records that received classifications
        classified_records = 0
        for field in ["primary_cet_area", "cet_classification", "technology_category"]:
            if field in classified_df.columns:
                classified_records = max(classified_records, classified_df[field].notna().sum())
        
        unclassified_records = total_records - classified_records
        
        return ChangesSummary(
            total_records=total_records,
            records_modified=classified_records,
            records_unchanged=unclassified_records,
            modification_rate=classified_records / total_records if total_records > 0 else 0.0,
            fields_added=fields_added,
            fields_modified=[],
            enrichment_sources={"cet_classification": classified_records},
        )
    
    def _create_empty_report(self, run_context: Dict[str, Any]) -> ModuleReport:
        """Create an empty report when no data is available.
        
        Args:
            run_context: Pipeline run context
            
        Returns:
            Empty ModuleReport
        """
        return self.create_module_report(
            run_id=run_context.get("run_id", "unknown"),
            stage="transform",
            total_records=0,
            records_processed=0,
            records_failed=0,
            duration_seconds=0.0,
            module_metrics={"error": "No classified DataFrame available"},
        )