"""Schemas for statistical and executive reporting."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field, field_validator


class StatisticalReportingConfig(BaseModel):
    """Configuration for statistical reporting and automated insights."""

    enabled: bool = True
    output_directory: str = Field(default="reports/statistics")
    report_types: list[str] = Field(
        default_factory=lambda: [
            "data_quality",
            "enrichment_performance",
            "pipeline_performance",
            "anomaly_detection",
            "success_metrics",
        ]
    )
    schedules: dict[str, Any] = Field(
        default_factory=lambda: {
            "daily": {
                "enabled": True,
                "hour": 2,
                "minute": 0,
                "include_summary": True,
            },
            "weekly": {
                "enabled": True,
                "weekday": "monday",
                "hour": 6,
                "minute": 0,
                "include_trends": True,
            },
        }
    )
    distribution: dict[str, Any] = Field(
        default_factory=lambda: {
            "email": {
                "enabled": True,
                "recipients": ["analytics_team@example.com"],
                "attach_reports": True,
            },
            "slack": {
                "enabled": True,
                "channel": "#analytics-updates",
                "include_summary": True,
            },
        }
    )
    sections: dict[str, Any] = Field(
        default_factory=lambda: {
            "pipeline_health": {
                "enabled": True,
                "include_validation_details": True,
                "include_loading_statistics": True,
            },
            "cet_classification": {
                "enabled": True,
                "include_confidence_distribution": True,
                "include_taxonomy_breakdown": True,
            },
            "transition_detection": {
                "enabled": True,
                "include_success_stories": True,
                "include_trend_analysis": True,
            },
        }
    )
    insights: dict[str, Any] = Field(
        default_factory=lambda: {
            "anomaly_detection": {
                "enabled": True,
                "sensitivity": "medium",
                "lookback_periods": 5,
            },
            "recommendations": {
                "enabled": True,
                "include_actionable_steps": True,
            },
            "success_stories": {
                "enabled": True,
                "min_impact_threshold": 0.8,
            },
        }
    )
    formats: dict[str, Any] = Field(
        default_factory=lambda: {
            "html": {
                "include_interactive_charts": True,
                "chart_library": "plotly",
                "theme": "default",
            },
            "json": {
                "include_raw_data": False,
                "pretty_print": True,
            },
            "markdown": {
                "max_length": 2000,
                "include_links": True,
            },
            "executive": {
                "include_visualizations": True,
                "focus_areas": ["impact", "quality", "trends"],
            },
        }
    )
    cicd: dict[str, Any] = Field(
        default_factory=lambda: {
            "github_actions": {
                "enabled": True,
                "upload_artifacts": True,
                "post_pr_comments": True,
                "artifact_retention_days": 30,
            },
            "report_comparison": {
                "enabled": True,
                "baseline_comparison": True,
                "trend_analysis_periods": [7, 30, 90],
            },
        }
    )
    quality_thresholds: dict[str, Any] = Field(
        default_factory=lambda: {
            "data_completeness_warning": 0.90,
            "data_completeness_error": 0.80,
            "enrichment_success_warning": 0.85,
            "enrichment_success_error": 0.70,
            "performance_degradation_warning": 1.5,
            "performance_degradation_error": 2.0,
        }
    )

    @field_validator("quality_thresholds")
    @classmethod
    def validate_quality_thresholds(cls, value: Mapping[str, Any]) -> dict[str, float]:
        if not isinstance(value, Mapping):
            raise TypeError("Expected a mapping for quality thresholds")

        normalized: dict[str, float] = {}
        for key, raw in value.items():
            try:
                number = float(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{key} must be a number, got {raw!r}") from exc

            if "warning" in key or "error" in key:
                if key.startswith(("data_completeness", "enrichment_success")):
                    if not (0.0 <= number <= 1.0):
                        raise ValueError(f"{key} must be between 0.0 and 1.0, got {number}")
                elif key.startswith("performance_degradation") and number < 1.0:
                    raise ValueError(f"{key} must be >= 1.0 (1.0 = no degradation), got {number}")

            normalized[key] = number
        return normalized


__all__ = ["StatisticalReportingConfig"]
