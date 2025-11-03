"""
Audit trail and lineage tracking for fiscal returns analysis.

This module implements comprehensive logging of parameter values and transformation steps,
tracking data lineage from source awards to final estimates with structured audit logs.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from ..config.loader import get_config


class FiscalAuditTrail:
    """Track audit trail and data lineage for fiscal returns analysis.

    This class maintains a structured audit log documenting all parameters,
    transformations, and assumptions used in the analysis pipeline.
    """

    def __init__(self, analysis_id: str | None = None, config: Any | None = None):
        """Initialize the audit trail.

        Args:
            analysis_id: Optional analysis identifier (generates UUID if not provided)
            config: Optional configuration override
        """
        import uuid

        self.analysis_id = analysis_id or str(uuid.uuid4())
        self.config = config or get_config()
        self.base_year = self.config.fiscal_analysis.base_year

        # Audit log structure
        self.audit_log: dict[str, Any] = {
            "analysis_id": self.analysis_id,
            "analysis_started_at": datetime.now().isoformat(),
            "base_year": self.base_year,
            "configuration": {},
            "transformations": [],
            "assumptions": [],
            "data_lineage": {},
            "quality_metrics": {},
        }

        # Track data lineage
        self.lineage: dict[str, list[str]] = {}  # award_id -> [transformation steps]

    def log_configuration(self) -> None:
        """Log configuration parameters used in analysis."""
        fiscal_config = self.config.fiscal_analysis

        self.audit_log["configuration"] = {
            "base_year": fiscal_config.base_year,
            "inflation_source": fiscal_config.inflation_source,
            "naics_crosswalk_version": fiscal_config.naics_crosswalk_version,
            "stateio_model_version": fiscal_config.stateio_model_version,
            "tax_parameters": {
                "individual_income_tax": fiscal_config.tax_parameters.individual_income_tax,
                "payroll_tax": fiscal_config.tax_parameters.payroll_tax,
                "corporate_income_tax": fiscal_config.tax_parameters.corporate_income_tax,
                "excise_tax": fiscal_config.tax_parameters.excise_tax,
            },
            "quality_thresholds": fiscal_config.quality_thresholds,
            "performance": fiscal_config.performance,
        }

        logger.debug(f"Logged configuration for analysis {self.analysis_id}")

    def log_transformation(
        self,
        step_name: str,
        input_count: int,
        output_count: int,
        parameters: dict[str, Any] | None = None,
        quality_metrics: dict[str, Any] | None = None,
    ) -> None:
        """Log a transformation step.

        Args:
            step_name: Name of transformation step (e.g., "NAICS_enrichment")
            input_count: Number of input records
            output_count: Number of output records
            parameters: Optional step-specific parameters
            quality_metrics: Optional quality metrics for this step
        """
        transformation = {
            "step_name": step_name,
            "timestamp": datetime.now().isoformat(),
            "input_count": input_count,
            "output_count": output_count,
            "parameters": parameters or {},
            "quality_metrics": quality_metrics or {},
        }

        self.audit_log["transformations"].append(transformation)

        logger.debug(
            f"Logged transformation: {step_name} ({input_count} -> {output_count} records)"
        )

    def log_assumption(
        self,
        assumption_type: str,
        description: str,
        rationale: str | None = None,
        impact: str | None = None,
    ) -> None:
        """Log an assumption made during analysis.

        Args:
            assumption_type: Type of assumption (e.g., "tax_rate", "multiplier")
            description: Description of assumption
            rationale: Rationale for assumption
            impact: Estimated impact of assumption
        """
        assumption = {
            "assumption_type": assumption_type,
            "description": description,
            "rationale": rationale,
            "impact": impact,
            "timestamp": datetime.now().isoformat(),
        }

        self.audit_log["assumptions"].append(assumption)

        logger.debug(f"Logged assumption: {assumption_type} - {description}")

    def track_lineage(
        self,
        award_id: str,
        transformation_step: str,
        output_id: str | None = None,
    ) -> None:
        """Track data lineage for a specific award.

        Args:
            award_id: Source award identifier
            transformation_step: Transformation step name
            output_id: Optional output identifier (shock_id, impact_id, etc.)
        """
        if award_id not in self.lineage:
            self.lineage[award_id] = []

        lineage_entry = {
            "step": transformation_step,
            "timestamp": datetime.now().isoformat(),
            "output_id": output_id,
        }

        self.lineage[award_id].append(lineage_entry)

    def log_quality_metrics(self, step_name: str, metrics: dict[str, Any]) -> None:
        """Log quality metrics for a transformation step.

        Args:
            step_name: Name of transformation step
            metrics: Quality metrics dictionary
        """
        self.audit_log["quality_metrics"][step_name] = metrics

    def finalize_audit_log(self) -> dict[str, Any]:
        """Finalize audit log with completion timestamp and lineage.

        Returns:
            Complete audit log dictionary
        """
        self.audit_log["analysis_completed_at"] = datetime.now().isoformat()
        self.audit_log["data_lineage"] = self.lineage
        self.audit_log["total_transformations"] = len(self.audit_log["transformations"])
        self.audit_log["total_assumptions"] = len(self.audit_log["assumptions"])

        logger.info(
            f"Finalized audit log for analysis {self.analysis_id} "
            f"({self.audit_log['total_transformations']} transformations, "
            f"{self.audit_log['total_assumptions']} assumptions)"
        )

        return self.audit_log

    def save_audit_log(self, output_path: Path | str | None = None) -> Path:
        """Save audit log to JSON file.

        Args:
            output_path: Optional output path (defaults to reports/fiscal_returns/)

        Returns:
            Path to saved audit log file
        """
        if output_path is None:
            output_dir = Path(
                self.config.fiscal_analysis.output.get("output_directory", "reports/fiscal_returns")
            )
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"audit_trail_{self.analysis_id}.json"
        else:
            output_path = Path(output_path)

        # Finalize log before saving
        log = self.finalize_audit_log()

        # Save to JSON
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w") as f:
            json.dump(log, f, indent=2, default=str)

        logger.info(f"Saved audit log to {output_path}")

        return output_path

    def get_audit_summary(self) -> dict[str, Any]:
        """Get summary of audit log.

        Returns:
            Summary dictionary with key metrics
        """
        return {
            "analysis_id": self.analysis_id,
            "total_transformations": len(self.audit_log["transformations"]),
            "total_assumptions": len(self.audit_log["assumptions"]),
            "awards_tracked": len(self.lineage),
            "analysis_started_at": self.audit_log["analysis_started_at"],
            "analysis_completed_at": self.audit_log.get("analysis_completed_at"),
        }


def create_audit_trail(
    analysis_id: str | None = None, config: Any | None = None
) -> FiscalAuditTrail:
    """Create a new audit trail instance.

    Args:
        analysis_id: Optional analysis identifier
        config: Optional configuration override

    Returns:
        FiscalAuditTrail instance
    """
    trail = FiscalAuditTrail(analysis_id=analysis_id, config=config)
    trail.log_configuration()
    return trail
