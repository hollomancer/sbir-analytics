"""Pydantic models for company categorization data.

This module provides data models for the company categorization system that
classifies SBIR companies as Product, Service, or Mixed based on their federal
contract portfolios from USAspending.

Models:
    - ContractClassification: Individual contract classification result
    - CompanyClassification: Aggregated company-level classification
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ContractClassification(BaseModel):
    """Classification result for a single federal contract/award.

    This model represents the classification of an individual contract based on
    PSC codes, contract type, pricing, description keywords, and SBIR phase.
    """

    # Core identification
    award_id: str = Field(..., description="Contract/award identifier")

    # Classification result
    classification: str = Field(
        ...,
        description="Classification result: Product, Service, or R&D"
    )
    method: str = Field(
        ...,
        description="Classification method used (e.g., psc_numeric, contract_type, description_inference)"
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Classification confidence score (0.0-1.0)"
    )

    # Original contract data fields
    psc: str | None = Field(None, description="Product Service Code")
    contract_type: str | None = Field(None, description="Contract type (e.g., CPFF, FFP)")
    pricing: str | None = Field(None, description="Pricing type (e.g., FFP, T&M)")
    description: str | None = Field(None, description="Award description")
    award_amount: float | None = Field(None, description="Award amount in USD")
    sbir_phase: str | None = Field(None, description="SBIR phase if applicable (I, II, III)")

    @field_validator("classification")
    @classmethod
    def validate_classification(cls, v: str) -> str:
        """Validate classification is one of the allowed values."""
        allowed = {"Product", "Service", "R&D"}
        if v not in allowed:
            raise ValueError(f"Classification must be one of {allowed}, got {v}")
        return v

    @field_validator("confidence")
    @classmethod
    def validate_confidence_range(cls, v: float) -> float:
        """Validate confidence is between 0.0 and 1.0."""
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"Confidence must be between 0.0 and 1.0, got {v}")
        return v

    @field_validator("sbir_phase")
    @classmethod
    def validate_sbir_phase(cls, v: str | None) -> str | None:
        """Validate SBIR phase if provided."""
        if v is None:
            return v
        allowed = {"I", "II", "III"}
        if v not in allowed:
            raise ValueError(f"SBIR phase must be one of {allowed}, got {v}")
        return v

    model_config = ConfigDict(
        validate_assignment=True,
        str_strip_whitespace=True,
    )


class CompanyClassification(BaseModel):
    """Classification result for a company based on aggregated contract portfolio.

    This model represents the aggregated classification of a company based on
    dollar-weighted analysis of all their federal contracts from USAspending.
    """

    # Core identification
    company_uei: str | None = Field(None, description="Company UEI (optional)")
    company_name: str = Field(..., description="Company name")

    # Classification result
    classification: str = Field(
        ...,
        description="Company classification: Product-leaning, Service-leaning, R&D-leaning, Mixed, or Uncertain"
    )
    product_pct: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Percentage of dollars from product contracts"
    )
    service_pct: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Percentage of dollars from service contracts"
    )
    rd_pct: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Percentage of dollars from R&D contracts"
    )
    confidence: str = Field(
        ...,
        description="Confidence level: Low, Medium, or High"
    )

    # Portfolio metadata
    award_count: int = Field(..., description="Total number of contracts in portfolio")
    psc_family_count: int = Field(..., description="Number of distinct PSC families")
    total_dollars: float = Field(..., description="Total contract dollars")
    product_dollars: float = Field(..., description="Product contract dollars")
    service_dollars: float = Field(..., description="Service contract dollars")
    rd_dollars: float = Field(..., description="R&D contract dollars")

    # Override information
    override_reason: str | None = Field(
        None,
        description="Reason for override if applied (e.g., high_psc_diversity, insufficient_awards)"
    )

    # Contract details (for audit trail)
    contracts: list[ContractClassification] = Field(
        default_factory=list,
        description="Individual contract classifications"
    )

    @field_validator("classification")
    @classmethod
    def validate_classification(cls, v: str) -> str:
        """Validate classification is one of the allowed values."""
        allowed = {"Product-leaning", "Service-leaning", "R&D-leaning", "Mixed", "Uncertain"}
        if v not in allowed:
            raise ValueError(f"Classification must be one of {allowed}, got {v}")
        return v

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: str) -> str:
        """Validate confidence level is one of the allowed values."""
        allowed = {"Low", "Medium", "High"}
        if v not in allowed:
            raise ValueError(f"Confidence must be one of {allowed}, got {v}")
        return v

    @field_validator("product_pct", "service_pct", "rd_pct")
    @classmethod
    def validate_percentage_range(cls, v: float) -> float:
        """Validate percentage is between 0.0 and 100.0."""
        if not (0.0 <= v <= 100.0):
            raise ValueError(f"Percentage must be between 0.0 and 100.0, got {v}")
        return round(v, 2)

    @field_validator("award_count", "psc_family_count")
    @classmethod
    def validate_count_non_negative(cls, v: int) -> int:
        """Validate count is non-negative."""
        if v < 0:
            raise ValueError(f"Count must be non-negative, got {v}")
        return v

    @field_validator("total_dollars", "product_dollars", "service_dollars", "rd_dollars")
    @classmethod
    def validate_dollars_non_negative(cls, v: float) -> float:
        """Validate dollar amount is non-negative."""
        if v < 0:
            raise ValueError(f"Dollar amount must be non-negative, got {v}")
        return v

    model_config = ConfigDict(
        validate_assignment=True,
        str_strip_whitespace=True,
    )
