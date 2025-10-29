"""Pipeline validator for E2E testing.

This module provides comprehensive validation of the SBIR ETL pipeline stages,
including extraction, enrichment, and Neo4j graph validation.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

import pandas as pd
from loguru import logger
from neo4j import Session
from pydantic import BaseModel, Field

from src.loaders.neo4j_client import Neo4jClient
from src.models.quality import QualityIssue, QualitySeverity


class ValidationStage(str, Enum):
    """Pipeline stages that can be validated."""
    
    EXTRACTION = "extraction"
    VALIDATION = "validation"
    ENRICHMENT = "enrichment"
    TRANSFORMATION = "transformation"
    LOADING = "loading"


class ValidationStatus(str, Enum):
    """Validation result status."""
    
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


@dataclass
class ValidationCheck:
    """Individual validation check result."""
    
    name: str
    status: ValidationStatus
    message: str
    expected: Optional[Any] = None
    actual: Optional[Any] = None
    threshold: Optional[float] = None
    severity: QualitySeverity = QualitySeverity.MEDIUM
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StageValidationResult:
    """Validation result for a single pipeline stage."""
    
    stage: ValidationStage
    status: ValidationStatus
    duration_seconds: float
    checks: List[ValidationCheck] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def passed_checks(self) -> List[ValidationCheck]:
        """Get all checks that passed."""
        return [c for c in self.checks if c.status == ValidationStatus.PASSED]
    
    @property
    def failed_checks(self) -> List[ValidationCheck]:
        """Get all checks that failed."""
        return [c for c in self.checks if c.status == ValidationStatus.FAILED]
    
    @property
    def warning_checks(self) -> List[ValidationCheck]:
        """Get all checks with warnings."""
        return [c for c in self.checks if c.status == ValidationStatus.WARNING]


class PipelineValidator:
    """Comprehensive pipeline validator for E2E testing."""
    
    def __init__(self, neo4j_client: Optional[Neo4jClient] = None):
        """Initialize pipeline validator.
        
        Args:
            neo4j_client: Optional Neo4j client for graph validation
        """
        self.neo4j_client = neo4j_client
        self.logger = logger.bind(component="pipeline_validator")
    
    def validate_extraction_stage(
        self,
        raw_data: pd.DataFrame,
        expected_columns: Optional[List[str]] = None,
        min_records: int = 1,
        max_records: Optional[int] = None
    ) -> StageValidationResult:
        """Validate data extraction stage.
        
        Args:
            raw_data: Raw extracted DataFrame
            expected_columns: List of expected column names
            min_records: Minimum expected record count
            max_records: Maximum expected record count
            
        Returns:
            StageValidationResult with extraction validation results
        """
        start_time = datetime.now()
        checks = []
        
        # Record count validation
        record_count = len(raw_data)
        if record_count < min_records:
            checks.append(ValidationCheck(
                name="minimum_record_count",
                status=ValidationStatus.FAILED,
                message=f"Record count {record_count} below minimum {min_records}",
                expected=min_records,
                actual=record_count,
                severity=QualitySeverity.CRITICAL
            ))
        else:
            checks.append(ValidationCheck(
                name="minimum_record_count",
                status=ValidationStatus.PASSED,
                message=f"Record count {record_count} meets minimum requirement",
                expected=min_records,
                actual=record_count
            ))
        
        if max_records and record_count > max_records:
            checks.append(ValidationCheck(
                name="maximum_record_count",
                status=ValidationStatus.WARNING,
                message=f"Record count {record_count} exceeds expected maximum {max_records}",
                expected=max_records,
                actual=record_count,
                severity=QualitySeverity.LOW
            ))
        
        # Column validation
        if expected_columns:
            missing_columns = set(expected_columns) - set(raw_data.columns)
            if missing_columns:
                checks.append(ValidationCheck(
                    name="required_columns",
                    status=ValidationStatus.FAILED,
                    message=f"Missing required columns: {list(missing_columns)}",
                    expected=expected_columns,
                    actual=list(raw_data.columns),
                    severity=QualitySeverity.CRITICAL
                ))
            else:
                checks.append(ValidationCheck(
                    name="required_columns",
                    status=ValidationStatus.PASSED,
                    message="All required columns present",
                    expected=expected_columns,
                    actual=list(raw_data.columns)
                ))
        
        # Data type validation
        null_columns = raw_data.columns[raw_data.isnull().all()].tolist()
        if null_columns:
            checks.append(ValidationCheck(
                name="null_columns",
                status=ValidationStatus.WARNING,
                message=f"Columns with all null values: {null_columns}",
                actual=null_columns,
                severity=QualitySeverity.MEDIUM
            ))
        
        # Schema compliance check
        duplicate_columns = raw_data.columns[raw_data.columns.duplicated()].tolist()
        if duplicate_columns:
            checks.append(ValidationCheck(
                name="duplicate_columns",
                status=ValidationStatus.FAILED,
                message=f"Duplicate column names found: {duplicate_columns}",
                actual=duplicate_columns,
                severity=QualitySeverity.HIGH
            ))
        
        duration = (datetime.now() - start_time).total_seconds()
        
        # Determine overall status
        failed_checks = [c for c in checks if c.status == ValidationStatus.FAILED]
        overall_status = ValidationStatus.FAILED if failed_checks else ValidationStatus.PASSED
        
        return StageValidationResult(
            stage=ValidationStage.EXTRACTION,
            status=overall_status,
            duration_seconds=duration,
            checks=checks,
            metadata={
                "record_count": record_count,
                "column_count": len(raw_data.columns),
                "columns": list(raw_data.columns),
                "memory_usage_mb": raw_data.memory_usage(deep=True).sum() / 1024 / 1024
            }
        )
    
    def validate_enrichment_stage(
        self,
        enriched_data: pd.DataFrame,
        original_data: pd.DataFrame,
        min_match_rate: float = 0.7,
        expected_enrichment_columns: Optional[List[str]] = None
    ) -> StageValidationResult:
        """Validate data enrichment stage.
        
        Args:
            enriched_data: Enriched DataFrame
            original_data: Original DataFrame before enrichment
            min_match_rate: Minimum acceptable match rate
            expected_enrichment_columns: Expected enrichment columns
            
        Returns:
            StageValidationResult with enrichment validation results
        """
        start_time = datetime.now()
        checks = []
        
        # Record count preservation
        original_count = len(original_data)
        enriched_count = len(enriched_data)
        
        if enriched_count != original_count:
            checks.append(ValidationCheck(
                name="record_count_preservation",
                status=ValidationStatus.FAILED,
                message=f"Record count changed during enrichment: {original_count} -> {enriched_count}",
                expected=original_count,
                actual=enriched_count,
                severity=QualitySeverity.HIGH
            ))
        else:
            checks.append(ValidationCheck(
                name="record_count_preservation",
                status=ValidationStatus.PASSED,
                message="Record count preserved during enrichment",
                expected=original_count,
                actual=enriched_count
            ))
        
        # Enrichment columns validation
        if expected_enrichment_columns:
            missing_enrichment_cols = set(expected_enrichment_columns) - set(enriched_data.columns)
            if missing_enrichment_cols:
                checks.append(ValidationCheck(
                    name="enrichment_columns",
                    status=ValidationStatus.FAILED,
                    message=f"Missing enrichment columns: {list(missing_enrichment_cols)}",
                    expected=expected_enrichment_columns,
                    actual=[col for col in enriched_data.columns if col not in original_data.columns],
                    severity=QualitySeverity.HIGH
                ))
            else:
                checks.append(ValidationCheck(
                    name="enrichment_columns",
                    status=ValidationStatus.PASSED,
                    message="All expected enrichment columns present",
                    expected=expected_enrichment_columns,
                    actual=[col for col in enriched_data.columns if col not in original_data.columns]
                ))
        
        # Match rate validation
        match_rate = self._calculate_match_rate(enriched_data)
        if match_rate < min_match_rate:
            checks.append(ValidationCheck(
                name="match_rate",
                status=ValidationStatus.FAILED,
                message=f"Match rate {match_rate:.1%} below threshold {min_match_rate:.1%}",
                expected=min_match_rate,
                actual=match_rate,
                threshold=min_match_rate,
                severity=QualitySeverity.HIGH
            ))
        else:
            checks.append(ValidationCheck(
                name="match_rate",
                status=ValidationStatus.PASSED,
                message=f"Match rate {match_rate:.1%} meets threshold",
                expected=min_match_rate,
                actual=match_rate,
                threshold=min_match_rate
            ))
        
        # Quality metrics validation
        quality_metrics = self._calculate_enrichment_quality_metrics(enriched_data)
        
        duration = (datetime.now() - start_time).total_seconds()
        
        # Determine overall status
        failed_checks = [c for c in checks if c.status == ValidationStatus.FAILED]
        overall_status = ValidationStatus.FAILED if failed_checks else ValidationStatus.PASSED
        
        return StageValidationResult(
            stage=ValidationStage.ENRICHMENT,
            status=overall_status,
            duration_seconds=duration,
            checks=checks,
            metadata={
                "match_rate": match_rate,
                "quality_metrics": quality_metrics,
                "enrichment_columns": [col for col in enriched_data.columns if col not in original_data.columns]
            }
        )
    
    def validate_neo4j_graph(
        self,
        expected_node_types: Optional[List[str]] = None,
        expected_relationships: Optional[List[str]] = None,
        min_nodes: int = 1,
        min_relationships: int = 0
    ) -> StageValidationResult:
        """Validate Neo4j graph structure and content.
        
        Args:
            expected_node_types: Expected node labels
            expected_relationships: Expected relationship types
            min_nodes: Minimum expected node count
            min_relationships: Minimum expected relationship count
            
        Returns:
            StageValidationResult with Neo4j validation results
        """
        start_time = datetime.now()
        checks = []
        
        if not self.neo4j_client:
            checks.append(ValidationCheck(
                name="neo4j_client",
                status=ValidationStatus.SKIPPED,
                message="Neo4j client not available for validation",
                severity=QualitySeverity.LOW
            ))
            return StageValidationResult(
                stage=ValidationStage.LOADING,
                status=ValidationStatus.SKIPPED,
                duration_seconds=0,
                checks=checks
            )
        
        try:
            with self.neo4j_client.session() as session:
                # Node count validation
                node_count = self._get_total_node_count(session)
                if node_count < min_nodes:
                    checks.append(ValidationCheck(
                        name="minimum_node_count",
                        status=ValidationStatus.FAILED,
                        message=f"Node count {node_count} below minimum {min_nodes}",
                        expected=min_nodes,
                        actual=node_count,
                        severity=QualitySeverity.CRITICAL
                    ))
                else:
                    checks.append(ValidationCheck(
                        name="minimum_node_count",
                        status=ValidationStatus.PASSED,
                        message=f"Node count {node_count} meets minimum requirement",
                        expected=min_nodes,
                        actual=node_count
                    ))
                
                # Relationship count validation
                rel_count = self._get_total_relationship_count(session)
                if rel_count < min_relationships:
                    checks.append(ValidationCheck(
                        name="minimum_relationship_count",
                        status=ValidationStatus.FAILED,
                        message=f"Relationship count {rel_count} below minimum {min_relationships}",
                        expected=min_relationships,
                        actual=rel_count,
                        severity=QualitySeverity.HIGH
                    ))
                else:
                    checks.append(ValidationCheck(
                        name="minimum_relationship_count",
                        status=ValidationStatus.PASSED,
                        message=f"Relationship count {rel_count} meets minimum requirement",
                        expected=min_relationships,
                        actual=rel_count
                    ))
                
                # Node type validation
                if expected_node_types:
                    actual_node_types = self._get_node_types(session)
                    missing_types = set(expected_node_types) - set(actual_node_types)
                    if missing_types:
                        checks.append(ValidationCheck(
                            name="expected_node_types",
                            status=ValidationStatus.FAILED,
                            message=f"Missing expected node types: {list(missing_types)}",
                            expected=expected_node_types,
                            actual=actual_node_types,
                            severity=QualitySeverity.HIGH
                        ))
                    else:
                        checks.append(ValidationCheck(
                            name="expected_node_types",
                            status=ValidationStatus.PASSED,
                            message="All expected node types present",
                            expected=expected_node_types,
                            actual=actual_node_types
                        ))
                
                # Relationship type validation
                if expected_relationships:
                    actual_rel_types = self._get_relationship_types(session)
                    missing_rel_types = set(expected_relationships) - set(actual_rel_types)
                    if missing_rel_types:
                        checks.append(ValidationCheck(
                            name="expected_relationship_types",
                            status=ValidationStatus.FAILED,
                            message=f"Missing expected relationship types: {list(missing_rel_types)}",
                            expected=expected_relationships,
                            actual=actual_rel_types,
                            severity=QualitySeverity.HIGH
                        ))
                    else:
                        checks.append(ValidationCheck(
                            name="expected_relationship_types",
                            status=ValidationStatus.PASSED,
                            message="All expected relationship types present",
                            expected=expected_relationships,
                            actual=actual_rel_types
                        ))
                
                # Graph connectivity validation
                connectivity_check = self._validate_graph_connectivity(session)
                checks.append(connectivity_check)
                
        except Exception as e:
            checks.append(ValidationCheck(
                name="neo4j_connection",
                status=ValidationStatus.FAILED,
                message=f"Failed to connect to Neo4j: {str(e)}",
                severity=QualitySeverity.CRITICAL
            ))
        
        duration = (datetime.now() - start_time).total_seconds()
        
        # Determine overall status
        failed_checks = [c for c in checks if c.status == ValidationStatus.FAILED]
        overall_status = ValidationStatus.FAILED if failed_checks else ValidationStatus.PASSED
        
        return StageValidationResult(
            stage=ValidationStage.LOADING,
            status=overall_status,
            duration_seconds=duration,
            checks=checks,
            metadata={
                "node_count": node_count if 'node_count' in locals() else 0,
                "relationship_count": rel_count if 'rel_count' in locals() else 0,
                "node_types": actual_node_types if 'actual_node_types' in locals() else [],
                "relationship_types": actual_rel_types if 'actual_rel_types' in locals() else []
            }
        )
    
    def _calculate_match_rate(self, enriched_data: pd.DataFrame) -> float:
        """Calculate enrichment match rate from enriched data."""
        if len(enriched_data) == 0:
            return 0.0
        
        # Look for common enrichment match columns
        match_columns = [col for col in enriched_data.columns if 'match' in col.lower()]
        if not match_columns:
            return 0.0
        
        # Use the first match column to determine match rate
        match_col = match_columns[0]
        matched_count = enriched_data[match_col].notna().sum()
        return matched_count / len(enriched_data)
    
    def _calculate_enrichment_quality_metrics(self, enriched_data: pd.DataFrame) -> Dict[str, Any]:
        """Calculate quality metrics for enriched data."""
        metrics = {}
        
        # Match method distribution
        match_method_col = None
        for col in enriched_data.columns:
            if 'match_method' in col.lower():
                match_method_col = col
                break
        
        if match_method_col:
            method_counts = enriched_data[match_method_col].value_counts()
            metrics['match_methods'] = method_counts.to_dict()
        
        # Match score statistics
        match_score_col = None
        for col in enriched_data.columns:
            if 'match_score' in col.lower():
                match_score_col = col
                break
        
        if match_score_col:
            scores = enriched_data[match_score_col].dropna()
            if len(scores) > 0:
                metrics['match_score_stats'] = {
                    'mean': float(scores.mean()),
                    'median': float(scores.median()),
                    'min': float(scores.min()),
                    'max': float(scores.max()),
                    'std': float(scores.std()) if len(scores) > 1 else 0.0
                }
        
        return metrics
    
    def _get_total_node_count(self, session: Session) -> int:
        """Get total node count from Neo4j."""
        result = session.run("MATCH (n) RETURN count(n) as count")
        return result.single()["count"]
    
    def _get_total_relationship_count(self, session: Session) -> int:
        """Get total relationship count from Neo4j."""
        result = session.run("MATCH ()-[r]->() RETURN count(r) as count")
        return result.single()["count"]
    
    def _get_node_types(self, session: Session) -> List[str]:
        """Get all node types (labels) from Neo4j."""
        result = session.run("CALL db.labels()")
        try:
            return [record["label"] for record in result]
        except (TypeError, AttributeError):
            # Handle mock objects that might not have proper record structure
            return [getattr(record, 'label', str(record)) for record in result]
    
    def _get_relationship_types(self, session: Session) -> List[str]:
        """Get all relationship types from Neo4j."""
        result = session.run("CALL db.relationshipTypes()")
        try:
            return [record["relationshipType"] for record in result]
        except (TypeError, AttributeError):
            # Handle mock objects that might not have proper record structure
            return [getattr(record, 'relationshipType', str(record)) for record in result]
    
    def _validate_graph_connectivity(self, session: Session) -> ValidationCheck:
        """Validate basic graph connectivity."""
        try:
            # Check for isolated nodes (nodes with no relationships)
            result = session.run("""
                MATCH (n)
                WHERE NOT (n)--()
                RETURN count(n) as isolated_count
            """)
            record = result.single()
            isolated_count = record["isolated_count"]
            
            if isolated_count > 0:
                return ValidationCheck(
                    name="graph_connectivity",
                    status=ValidationStatus.WARNING,
                    message=f"Found {isolated_count} isolated nodes with no relationships",
                    actual=isolated_count,
                    severity=QualitySeverity.MEDIUM,
                    details={"isolated_nodes": isolated_count}
                )
            else:
                return ValidationCheck(
                    name="graph_connectivity",
                    status=ValidationStatus.PASSED,
                    message="All nodes have at least one relationship",
                    actual=isolated_count
                )
        except KeyError as e:
            return ValidationCheck(
                name="graph_connectivity",
                status=ValidationStatus.FAILED,
                message=f"Failed to validate graph connectivity: missing key {str(e)}",
                severity=QualitySeverity.MEDIUM
            )
        except Exception as e:
            return ValidationCheck(
                name="graph_connectivity",
                status=ValidationStatus.FAILED,
                message=f"Failed to validate graph connectivity: {str(e)}",
                severity=QualitySeverity.MEDIUM
            )