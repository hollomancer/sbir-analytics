"""Configuration schemas for fiscal analysis modules."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field, field_validator

from .common import PercentageMappingMixin


class TaxParameterConfig(BaseModel):
    """Configuration for federal tax calculation parameters."""

    individual_income_tax: dict[str, Any] = Field(
        default_factory=lambda: {
            "effective_rate": 0.22,
            "progressive_rates": {
                "10_percent": 0.10,
                "12_percent": 0.12,
                "22_percent": 0.22,
                "24_percent": 0.24,
                "32_percent": 0.32,
                "35_percent": 0.35,
                "37_percent": 0.37,
            },
            "standard_deduction": 13850,
        }
    )
    payroll_tax: dict[str, Any] = Field(
        default_factory=lambda: {
            "social_security_rate": 0.062,
            "medicare_rate": 0.0145,
            "unemployment_rate": 0.006,
            "wage_base_limit": 160200,
        }
    )
    corporate_income_tax: dict[str, Any] = Field(
        default_factory=lambda: {
            "federal_rate": 0.21,
            "effective_rate": 0.18,
        }
    )
    excise_tax: dict[str, Any] = Field(
        default_factory=lambda: {
            "fuel_tax_rate": 0.184,
            "general_rate": 0.03,
        }
    )

    @field_validator("individual_income_tax", "payroll_tax", "corporate_income_tax", "excise_tax")
    @classmethod
    def validate_tax_parameters(cls, value: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise TypeError("Expected a mapping for tax parameters")

        normalized: dict[str, Any] = dict(value)
        for key, raw in normalized.items():
            if "rate" in key and isinstance(raw, int | float):
                rate = float(raw)
                if not (0.0 <= rate <= 1.0):
                    raise ValueError(f"Tax rate {key} must be between 0.0 and 1.0, got {rate}")
                normalized[key] = rate
        return normalized


class SensitivityConfig(BaseModel):
    """Configuration for sensitivity analysis and uncertainty quantification."""

    parameter_sweep: dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": True,
            "method": "monte_carlo",
            "num_scenarios": 1000,
            "random_seed": 42,
        }
    )
    uncertainty_parameters: dict[str, Any] = Field(
        default_factory=lambda: {
            "tax_rates": {
                "variation_percent": 0.10,
                "distribution": "normal",
            },
            "multipliers": {
                "variation_percent": 0.15,
                "distribution": "normal",
            },
            "inflation_adjustment": {
                "variation_percent": 0.05,
                "distribution": "normal",
            },
        }
    )
    confidence_intervals: dict[str, Any] = Field(
        default_factory=lambda: {
            "levels": [0.90, 0.95, 0.99],
            "method": "percentile",
            "bootstrap_samples": 1000,
        }
    )
    performance: dict[str, Any] = Field(
        default_factory=lambda: {
            "max_scenarios_parallel": 10,
            "timeout_seconds": 3600,
            "memory_limit_gb": 8,
        }
    )

    @field_validator("uncertainty_parameters")
    @classmethod
    def validate_uncertainty_parameters(cls, value: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise TypeError("Expected a mapping for uncertainty parameters")

        normalized: dict[str, Any] = dict(value)
        for param_name, param_config in normalized.items():
            if isinstance(param_config, dict) and "variation_percent" in param_config:
                variation = param_config["variation_percent"]
                if isinstance(variation, int | float):
                    variation = float(variation)
                    if not (0.0 <= variation <= 1.0):
                        raise ValueError(
                            f"Variation percent for {param_name} must be between 0.0 and 1.0, got {variation}"
                        )
                    param_config["variation_percent"] = variation
        return normalized


class FiscalAnalysisConfig(PercentageMappingMixin, BaseModel):
    """Configuration for SBIR fiscal returns analysis."""

    base_year: int = Field(default=2023, description="Base year for inflation adjustment")
    inflation_source: str = Field(
        default="bea_gdp_deflator", description="Source for inflation data"
    )
    naics_crosswalk_version: str = Field(
        default="2022", description="NAICS-to-BEA crosswalk version"
    )
    stateio_model_version: str = Field(default="v2.1", description="StateIO model version")
    tax_parameters: TaxParameterConfig = Field(
        default_factory=TaxParameterConfig, description="Federal tax calculation parameters"
    )
    sensitivity_parameters: SensitivityConfig = Field(
        default_factory=SensitivityConfig,
        description="Sensitivity analysis and uncertainty quantification parameters",
    )
    quality_thresholds: dict[str, Any] = Field(
        default_factory=lambda: {
            "naics_coverage_rate": 0.85,
            "geographic_resolution_rate": 0.90,
            "inflation_adjustment_success": 0.95,
            "bea_sector_mapping_rate": 0.90,
        }
    )
    performance: dict[str, Any] = Field(
        default_factory=lambda: {
            "chunk_size": 10000,
            "parallel_processing": True,
            "max_workers": 4,
            "memory_limit_gb": 4,
            "timeout_seconds": 1800,
        }
    )
    output: dict[str, Any] = Field(
        default_factory=lambda: {
            "formats": ["json", "csv", "html"],
            "include_audit_trail": True,
            "include_sensitivity_analysis": True,
            "output_directory": "reports/fiscal_returns",
        }
    )

    @field_validator("base_year")
    @classmethod
    def validate_base_year(cls, value: int) -> int:
        if not (1980 <= value <= 2030):
            raise ValueError(f"Base year must be between 1980 and 2030, got {value}")
        return value

    @field_validator("quality_thresholds")
    @classmethod
    def validate_quality_thresholds(cls, value: Mapping[str, Any]) -> dict[str, float]:
        return cls._coerce_percentage_mapping(value, field_name="fiscal_quality")


__all__ = [
    "FiscalAnalysisConfig",
    "SensitivityConfig",
    "TaxParameterConfig",
]
