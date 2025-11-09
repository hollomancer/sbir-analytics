"""Patent analysis analyzer for statistical reporting.

This analyzer focuses on patent validation and loading operations, calculating
validation pass/fail rates, loading statistics (nodes created, relationships
established), and data quality scores for patent records.
"""

from typing import Any

import pandas as pd
from loguru import logger

from src.models.quality import ChangesSummary, DataHygieneMetrics, ModuleReport
from src.utils.reporting.analyzers.base_analyzer import AnalysisInsight, ModuleAnalyzer


class PatentAnalysisAnalyzer(ModuleAnalyzer):
    """Analyzer for patent validation and loading operations."""

    def __init__(self, config: dict[str, Any] | None = None):
        """Initialize patent analysis analyzer.

        Args:
            config: Optional configuration for analysis thresholds
        """
        super().__init__("patent_analysis", config)

        # Default thresholds - can be overridden by config
        self.thresholds = {
            "min_validation_pass_rate": self.config.get("min_validation_pass_rate", 0.95),
            "min_loading_success_rate": self.config.get("min_loading_success_rate", 0.98),
            "min_data_quality_score": self.config.get("min_data_quality_score", 0.85),
            "max_duplicate_rate": self.config.get("max_duplicate_rate", 0.05),
        }

        # Key patent fields to analyze
        self.patent_fields = [
            "grant_doc_num",
            "title",
            "grant_date",
            "inventor_names",
            "assignee_names",
            "abstract",
            "claims_count",
            "citations_count",
        ]

        # Neo4j node and relationship types
        self.node_types = ["Patent", "PatentAssignment", "PatentEntity", "Company"]
        self.relationship_types = ["ASSIGNED_VIA", "ASSIGNED_FROM", "ASSIGNED_TO", "OWNS"]

    def analyze(self, module_data: dict[str, Any]) -> ModuleReport:
        """Analyze patent data and generate comprehensive report.

        Args:
            module_data: Dictionary containing:
                - patent_df: Patent DataFrame
                - validation_results: Patent validation results
                - loading_results: Neo4j loading results
                - neo4j_stats: Neo4j database statistics
                - run_context: Pipeline run context

        Returns:
            ModuleReport with patent analysis results
        """
        logger.info("Starting patent analysis")

        patent_df = module_data.get("patent_df")
        validation_results = module_data.get("validation_results", {})
        loading_results = module_data.get("loading_results", {})
        neo4j_stats = module_data.get("neo4j_stats", {})
        run_context = module_data.get("run_context", {})

        if patent_df is None:
            logger.warning("No patent DataFrame provided for analysis")
            return self._create_empty_report(run_context)

        # Calculate key metrics
        key_metrics = self.get_key_metrics(module_data)

        # Generate insights
        insights = self.generate_insights(module_data)

        # Calculate data hygiene metrics
        data_hygiene = self._calculate_data_hygiene(patent_df, validation_results)

        # Calculate changes summary (for loading operations)
        changes_summary = self._calculate_changes_summary(loading_results, neo4j_stats)

        # Extract processing metrics
        total_records = len(patent_df) if patent_df is not None else 0
        records_processed = validation_results.get("valid_records", total_records)
        records_failed = validation_results.get("invalid_records", 0)
        duration_seconds = loading_results.get("duration_seconds", 0.0)

        # Create module report
        report = self.create_module_report(
            run_id=run_context.get("run_id", "unknown"),
            stage="load",
            total_records=total_records,
            records_processed=records_processed,
            records_failed=records_failed,
            duration_seconds=duration_seconds,
            module_metrics=key_metrics,
            data_hygiene=data_hygiene,
            changes_summary=changes_summary,
        )

        logger.info(f"Patent analysis complete: {len(insights)} insights generated")
        return report

    def get_key_metrics(self, module_data: dict[str, Any]) -> dict[str, Any]:
        """Extract key metrics from patent analysis data.

        Args:
            module_data: Module data containing patent DataFrame and results

        Returns:
            Dictionary of key patent analysis metrics
        """
        patent_df = module_data.get("patent_df")
        validation_results = module_data.get("validation_results", {})
        loading_results = module_data.get("loading_results", {})
        neo4j_stats = module_data.get("neo4j_stats", {})

        if patent_df is None:
            return {"error": "No patent DataFrame available"}

        total_records = len(patent_df)

        # Calculate validation metrics
        validation_metrics = self._calculate_validation_metrics(patent_df, validation_results)

        # Calculate loading statistics
        loading_statistics = self._calculate_loading_statistics(loading_results, neo4j_stats)

        # Calculate data quality scores
        quality_scores = self._calculate_quality_scores(patent_df, validation_results)

        # Calculate patent-specific metrics
        patent_metrics = self._calculate_patent_specific_metrics(patent_df)

        # Calculate relationship metrics
        relationship_metrics = self._calculate_relationship_metrics(neo4j_stats)

        return {
            "total_records": total_records,
            "validation_metrics": validation_metrics,
            "loading_statistics": loading_statistics,
            "quality_scores": quality_scores,
            "patent_metrics": patent_metrics,
            "relationship_metrics": relationship_metrics,
            "processing_duration_seconds": loading_results.get("duration_seconds", 0.0),
            "throughput_records_per_second": loading_results.get("records_per_second", 0.0),
        }

    def generate_insights(self, module_data: dict[str, Any]) -> list[AnalysisInsight]:
        """Generate automated insights for patent analysis.

        Args:
            module_data: Module data containing patent DataFrame and results

        Returns:
            List of analysis insights and recommendations
        """
        insights: list[Any] = []
        patent_df = module_data.get("patent_df")
        validation_results = module_data.get("validation_results", {})
        loading_results = module_data.get("loading_results", {})

        if patent_df is None:
            return insights

        # Analyze validation pass rate
        validation_pass_rate = validation_results.get("validation_pass_rate", 0.0)
        if validation_pass_rate < self.thresholds["min_validation_pass_rate"]:
            insights.append(
                AnalysisInsight(
                    category="validation_quality",
                    title="Low Patent Validation Pass Rate",
                    message=f"Patent validation pass rate ({validation_pass_rate:.1%}) is below threshold ({self.thresholds['min_validation_pass_rate']:.1%})",
                    severity="warning",
                    confidence=0.9,
                    affected_records=int(len(patent_df) * (1 - validation_pass_rate)),
                    recommendations=[
                        "Review patent data quality at source",
                        "Check validation rules for appropriateness",
                        "Investigate common validation failure patterns",
                        "Consider data cleaning before validation",
                    ],
                    metadata={
                        "current_rate": validation_pass_rate,
                        "threshold": self.thresholds["min_validation_pass_rate"],
                    },
                )
            )

        # Analyze loading success rate
        loading_success_rate = loading_results.get("loading_success_rate", 0.0)
        if loading_success_rate < self.thresholds["min_loading_success_rate"]:
            insights.append(
                AnalysisInsight(
                    category="loading_performance",
                    title="Low Patent Loading Success Rate",
                    message=f"Patent loading success rate ({loading_success_rate:.1%}) is below threshold ({self.thresholds['min_loading_success_rate']:.1%})",
                    severity="error",
                    confidence=0.95,
                    affected_records=int(len(patent_df) * (1 - loading_success_rate)),
                    recommendations=[
                        "Check Neo4j database connectivity and performance",
                        "Review constraint violations and duplicate handling",
                        "Investigate transaction timeout issues",
                        "Consider batch size optimization",
                    ],
                    metadata={
                        "current_rate": loading_success_rate,
                        "threshold": self.thresholds["min_loading_success_rate"],
                    },
                )
            )

        # Analyze data quality scores
        avg_quality_score = validation_results.get("average_quality_score", 0.0)
        if avg_quality_score < self.thresholds["min_data_quality_score"]:
            insights.append(
                AnalysisInsight(
                    category="data_quality",
                    title="Low Average Patent Data Quality",
                    message=f"Average patent data quality score ({avg_quality_score:.2f}) is below threshold ({self.thresholds['min_data_quality_score']:.2f})",
                    severity="warning",
                    confidence=0.8,
                    affected_records=len(patent_df),
                    recommendations=[
                        "Improve patent data extraction processes",
                        "Implement additional data cleaning steps",
                        "Review and update data quality validation rules",
                        "Consider data source quality improvements",
                    ],
                    metadata={
                        "current_score": avg_quality_score,
                        "threshold": self.thresholds["min_data_quality_score"],
                    },
                )
            )

        # Analyze duplicate rates
        duplicate_rate = validation_results.get("duplicate_rate", 0.0)
        if duplicate_rate > self.thresholds["max_duplicate_rate"]:
            insights.append(
                AnalysisInsight(
                    category="data_duplicates",
                    title="High Patent Duplicate Rate",
                    message=f"Patent duplicate rate ({duplicate_rate:.1%}) exceeds threshold ({self.thresholds['max_duplicate_rate']:.1%})",
                    severity="warning",
                    confidence=0.85,
                    affected_records=int(len(patent_df) * duplicate_rate),
                    recommendations=[
                        "Implement deduplication logic before loading",
                        "Review patent identifier uniqueness constraints",
                        "Investigate source of duplicate records",
                        "Consider merge strategies for duplicate patents",
                    ],
                    metadata={
                        "current_rate": duplicate_rate,
                        "threshold": self.thresholds["max_duplicate_rate"],
                    },
                )
            )

        # Analyze relationship creation success
        relationship_success_rate = loading_results.get("relationship_success_rate", 0.0)
        if relationship_success_rate < 0.9:  # High threshold for relationships
            insights.append(
                AnalysisInsight(
                    category="relationship_creation",
                    title="Patent Relationship Creation Issues",
                    message=f"Patent relationship creation success rate ({relationship_success_rate:.1%}) indicates potential issues",
                    severity="info",
                    confidence=0.7,
                    affected_records=int(len(patent_df) * (1 - relationship_success_rate)),
                    recommendations=[
                        "Review patent assignment data quality",
                        "Check entity matching logic for assignments",
                        "Validate relationship creation queries",
                        "Investigate orphaned patent records",
                    ],
                    metadata={"current_rate": relationship_success_rate},
                )
            )

        return insights

    def _calculate_validation_metrics(
        self, patent_df: pd.DataFrame, validation_results: dict[str, Any]
    ) -> dict[str, Any]:
        """Calculate patent validation metrics.

        Args:
            patent_df: Patent DataFrame
            validation_results: Validation results dictionary

        Returns:
            Dictionary with validation metrics
        """
        total_records = len(patent_df)

        # Extract validation results or calculate from DataFrame
        valid_records = validation_results.get("valid_records", 0)
        invalid_records = validation_results.get("invalid_records", 0)

        # If not provided, estimate from DataFrame quality
        if valid_records == 0 and invalid_records == 0:
            # Simple validation: records with required fields
            required_fields = ["grant_doc_num", "title", "grant_date"]
            valid_mask = patent_df[required_fields].notna().all(axis=1)
            valid_records = valid_mask.sum()
            invalid_records = total_records - valid_records

        validation_pass_rate = valid_records / total_records if total_records > 0 else 0.0

        # Calculate field-specific validation rates
        field_validation_rates = {}
        for field in self.patent_fields:
            if field in patent_df.columns:
                field_valid = patent_df[field].notna().sum()
                field_validation_rates[field] = field_valid / total_records

        return {
            "total_records": total_records,
            "valid_records": valid_records,
            "invalid_records": invalid_records,
            "validation_pass_rate": validation_pass_rate,
            "validation_fail_rate": 1.0 - validation_pass_rate,
            "field_validation_rates": field_validation_rates,
            "validation_errors": validation_results.get("validation_errors", []),
            "validation_warnings": validation_results.get("validation_warnings", []),
        }

    def _calculate_loading_statistics(
        self, loading_results: dict[str, Any], neo4j_stats: dict[str, Any]
    ) -> dict[str, Any]:
        """Calculate Neo4j loading statistics.

        Args:
            loading_results: Loading operation results
            neo4j_stats: Neo4j database statistics

        Returns:
            Dictionary with loading statistics
        """
        # Extract loading results
        nodes_created = loading_results.get("nodes_created", 0)
        relationships_created = loading_results.get("relationships_created", 0)
        loading_errors = loading_results.get("loading_errors", 0)
        loading_duration = loading_results.get("duration_seconds", 0.0)

        # Calculate loading rates
        total_operations = nodes_created + relationships_created
        loading_success_rate = 1.0 - (loading_errors / max(total_operations, 1))

        # Extract Neo4j statistics by node type
        nodes_by_type = {}
        relationships_by_type = {}

        for node_type in self.node_types:
            nodes_by_type[node_type] = neo4j_stats.get(f"{node_type}_nodes", 0)

        for rel_type in self.relationship_types:
            relationships_by_type[rel_type] = neo4j_stats.get(f"{rel_type}_relationships", 0)

        return {
            "nodes_created": nodes_created,
            "relationships_created": relationships_created,
            "loading_errors": loading_errors,
            "loading_success_rate": loading_success_rate,
            "loading_duration_seconds": loading_duration,
            "loading_throughput": total_operations / loading_duration
            if loading_duration > 0
            else 0.0,
            "nodes_by_type": nodes_by_type,
            "relationships_by_type": relationships_by_type,
            "constraint_violations": neo4j_stats.get("constraint_violations", 0),
            "index_usage": neo4j_stats.get("index_usage", {}),
        }

    def _calculate_quality_scores(
        self, patent_df: pd.DataFrame, validation_results: dict[str, Any]
    ) -> dict[str, Any]:
        """Calculate data quality scores for patent records.

        Args:
            patent_df: Patent DataFrame
            validation_results: Validation results

        Returns:
            Dictionary with quality score metrics
        """
        total_records = len(patent_df)

        # Calculate quality scores for each record
        quality_scores = []
        for _idx, row in patent_df.iterrows():
            # Completeness score (0-1)
            non_null_count = row.notna().sum()
            total_fields = len(row)
            completeness_score = non_null_count / total_fields

            # Validity score based on field-specific rules
            validity_score = 1.0

            # Check grant_doc_num format (should be numeric)
            if pd.notna(row.get("grant_doc_num")):
                try:
                    int(str(row["grant_doc_num"]).replace(",", ""))
                except (ValueError, TypeError):
                    validity_score -= 0.2

            # Check grant_date validity
            if pd.notna(row.get("grant_date")):
                try:
                    pd.to_datetime(row["grant_date"])
                except (ValueError, TypeError):
                    validity_score -= 0.2

            # Check title length (should be reasonable)
            if pd.notna(row.get("title")):
                title_len = len(str(row["title"]))
                if title_len < 10 or title_len > 500:
                    validity_score -= 0.1

            # Overall quality score
            quality_score = (completeness_score + max(0, validity_score)) / 2
            quality_scores.append(quality_score)

        quality_series = pd.Series(quality_scores)

        # Calculate quality distribution
        high_quality = (quality_series >= 0.8).sum()
        medium_quality = ((quality_series >= 0.6) & (quality_series < 0.8)).sum()
        low_quality = (quality_series < 0.6).sum()

        return {
            "total_records": total_records,
            "average_quality_score": float(quality_series.mean()),
            "median_quality_score": float(quality_series.median()),
            "min_quality_score": float(quality_series.min()),
            "max_quality_score": float(quality_series.max()),
            "quality_std": float(quality_series.std()),
            "high_quality_records": int(high_quality),
            "medium_quality_records": int(medium_quality),
            "low_quality_records": int(low_quality),
            "high_quality_rate": high_quality / total_records if total_records > 0 else 0,
            "medium_quality_rate": medium_quality / total_records if total_records > 0 else 0,
            "low_quality_rate": low_quality / total_records if total_records > 0 else 0,
        }

    def _calculate_patent_specific_metrics(self, patent_df: pd.DataFrame) -> dict[str, Any]:
        """Calculate patent-specific analysis metrics.

        Args:
            patent_df: Patent DataFrame

        Returns:
            Dictionary with patent-specific metrics
        """
        metrics = {}

        # Patent grant date distribution
        if "grant_date" in patent_df.columns:
            grant_dates = pd.to_datetime(patent_df["grant_date"], errors="coerce").dropna()
            if not grant_dates.empty:
                metrics["grant_date_range"] = {
                    "earliest": grant_dates.min().isoformat(),
                    "latest": grant_dates.max().isoformat(),
                    "span_years": (grant_dates.max() - grant_dates.min()).days / 365.25,
                }

                # Grant date distribution by year
                grant_years = grant_dates.dt.year.value_counts().sort_index()
                metrics["grants_by_year"] = grant_years.to_dict()

        # Patent title analysis
        if "title" in patent_df.columns:
            titles = patent_df["title"].dropna()
            if not titles.empty:
                title_lengths = titles.str.len()
                metrics["title_analysis"] = {
                    "average_length": float(title_lengths.mean()),
                    "median_length": float(title_lengths.median()),
                    "min_length": int(title_lengths.min()),
                    "max_length": int(title_lengths.max()),
                }

        # Inventor analysis
        if "inventor_names" in patent_df.columns:
            inventors = patent_df["inventor_names"].dropna()
            if not inventors.empty:
                # Count patents with multiple inventors (assuming semicolon separation)
                multi_inventor_count = inventors.str.contains(";", na=False).sum()
                metrics["inventor_analysis"] = {
                    "patents_with_inventors": len(inventors),
                    "patents_with_multiple_inventors": int(multi_inventor_count),
                    "multi_inventor_rate": multi_inventor_count / len(inventors),
                }

        # Assignee analysis
        if "assignee_names" in patent_df.columns:
            assignees = patent_df["assignee_names"].dropna()
            if not assignees.empty:
                # Count patents with assignees
                metrics["assignee_analysis"] = {
                    "patents_with_assignees": len(assignees),
                    "assignee_rate": len(assignees) / len(patent_df),
                }

        # Claims and citations analysis
        for field in ["claims_count", "citations_count"]:
            if field in patent_df.columns:
                values = pd.to_numeric(patent_df[field], errors="coerce").dropna()
                if not values.empty:
                    metrics[f"{field}_analysis"] = {
                        "average": float(values.mean()),
                        "median": float(values.median()),
                        "min": int(values.min()),
                        "max": int(values.max()),
                        "total": int(values.sum()),
                    }

        return metrics

    def _calculate_relationship_metrics(self, neo4j_stats: dict[str, Any]) -> dict[str, Any]:
        """Calculate patent relationship metrics from Neo4j statistics.

        Args:
            neo4j_stats: Neo4j database statistics

        Returns:
            Dictionary with relationship metrics
        """
        metrics = {}

        # Count relationships by type
        total_relationships = 0
        for rel_type in self.relationship_types:
            count = neo4j_stats.get(f"{rel_type}_relationships", 0)
            metrics[f"{rel_type}_count"] = count
            total_relationships += count

        metrics["total_relationships"] = total_relationships

        # Calculate relationship density (relationships per patent)
        patent_count = neo4j_stats.get("Patent_nodes", 0)
        if patent_count > 0:
            metrics["relationships_per_patent"] = total_relationships / patent_count

        # Assignment chain metrics
        assignment_count = neo4j_stats.get("PatentAssignment_nodes", 0)
        assigned_via_count = neo4j_stats.get("ASSIGNED_VIA_relationships", 0)

        if assignment_count > 0:
            metrics["assignment_coverage"] = assigned_via_count / assignment_count

        # Ownership metrics
        owns_relationships = neo4j_stats.get("OWNS_relationships", 0)
        company_count = neo4j_stats.get("Company_nodes", 0)

        if company_count > 0:
            metrics["patents_per_company"] = owns_relationships / company_count

        return metrics

    def _calculate_data_hygiene(
        self, patent_df: pd.DataFrame, validation_results: dict[str, Any]
    ) -> DataHygieneMetrics:
        """Calculate data hygiene metrics for patent data.

        Args:
            patent_df: Patent DataFrame
            validation_results: Validation results

        Returns:
            DataHygieneMetrics instance
        """
        total_records = len(patent_df)

        # Use validation results if available
        clean_records = validation_results.get("valid_records", 0)
        dirty_records = validation_results.get("invalid_records", 0)

        # If not available, calculate based on completeness
        if clean_records == 0 and dirty_records == 0:
            required_fields = ["grant_doc_num", "title", "grant_date"]
            clean_mask = patent_df[required_fields].notna().all(axis=1)
            clean_records = clean_mask.sum()
            dirty_records = total_records - clean_records

        # Calculate quality scores (reuse from quality_scores method)
        quality_metrics = self._calculate_quality_scores(patent_df, validation_results)

        return DataHygieneMetrics(
            total_records=total_records,
            clean_records=int(clean_records),
            dirty_records=int(dirty_records),
            clean_percentage=float(clean_records / total_records * 100)
            if total_records > 0
            else 0.0,
            quality_score_mean=quality_metrics["average_quality_score"],
            quality_score_median=quality_metrics["median_quality_score"],
            quality_score_std=quality_metrics["quality_std"],
            quality_score_min=quality_metrics["min_quality_score"],
            quality_score_max=quality_metrics["max_quality_score"],
            validation_pass_rate=float(clean_records / total_records) if total_records > 0 else 0.0,
            validation_errors=validation_results.get("error_count", dirty_records),
            validation_warnings=validation_results.get("warning_count", 0),
        )

    def _calculate_changes_summary(
        self, loading_results: dict[str, Any], neo4j_stats: dict[str, Any]
    ) -> ChangesSummary:
        """Calculate summary of changes made during patent loading.

        Args:
            loading_results: Loading operation results
            neo4j_stats: Neo4j database statistics

        Returns:
            ChangesSummary instance
        """
        # For patent loading, "changes" are the nodes and relationships created
        nodes_created = loading_results.get("nodes_created", 0)
        relationships_created = loading_results.get("relationships_created", 0)
        total_operations = nodes_created + relationships_created

        # Count by node type
        node_changes = {}
        for node_type in self.node_types:
            count = neo4j_stats.get(f"{node_type}_nodes", 0)
            if count > 0:
                node_changes[f"{node_type}_nodes_created"] = count

        # Count by relationship type
        relationship_changes = {}
        for rel_type in self.relationship_types:
            count = neo4j_stats.get(f"{rel_type}_relationships", 0)
            if count > 0:
                relationship_changes[f"{rel_type}_relationships_created"] = count

        return ChangesSummary(
            total_records=total_operations,
            records_modified=total_operations,
            records_unchanged=0,  # All operations create new data
            modification_rate=1.0,  # All records are "modifications" (creations)
            fields_added=list(node_changes.keys()) + list(relationship_changes.keys()),
            fields_modified=[],
            enrichment_sources={"neo4j_loading": total_operations},
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
            stage="load",
            total_records=0,
            records_processed=0,
            records_failed=0,
            duration_seconds=0.0,
            module_metrics={"error": "No patent DataFrame available"},
        )
