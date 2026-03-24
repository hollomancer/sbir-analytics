"""
Pydantic models for CET (Critical and Emerging Technology) classification.

These models represent:
- CET technology areas from the NSTC taxonomy
- Classification results with confidence scores
- Evidence statements supporting classifications
- Complete CET assessments combining classification and evidence
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class ClassificationLevel(str, Enum):
    """Classification confidence levels based on score thresholds."""

    HIGH = "High"  # Score ≥ 70
    MEDIUM = "Medium"  # Score 40-69
    LOW = "Low"  # Score < 40


class CETArea(BaseModel):
    """
    A Critical and Emerging Technology area from the NSTC taxonomy.

    Represents one of the 21 CET categories defined by the National Science
    and Technology Council (NSTC).
    """

    cet_id: str = Field(
        ..., description="Unique identifier for the CET area (e.g., 'artificial_intelligence')"
    )
    name: str = Field(..., description="Human-readable name (e.g., 'Artificial Intelligence')")
    definition: str = Field(..., description="Official NSTC definition of the technology area")
    keywords: list[str] = Field(
        default_factory=list, description="Keywords associated with this CET area"
    )
    negative_keywords: list[str] = Field(
        default_factory=list,
        description="Negative keywords that indicate false positives (reduce classification confidence)",
    )
    parent_cet_id: str | None = Field(
        None, description="Parent CET ID for hierarchical relationships"
    )
    taxonomy_version: str = Field(..., description="Taxonomy version (e.g., 'NSTC-2025Q1')")

    @field_validator("cet_id")
    @classmethod
    def validate_cet_id(cls, v: str) -> str:
        """Ensure CET ID is lowercase with underscores."""
        if not v.replace("_", "").isalnum():
            raise ValueError("CET ID must contain only alphanumeric characters and underscores")
        return v.lower()


class EvidenceStatement(BaseModel):
    """
    Evidence supporting a CET classification.

    Provides explainability by linking classifications to specific text excerpts
    from the source document (abstract, keywords, solicitation).
    """

    excerpt: str = Field(
        ..., description="Text excerpt supporting the classification (max 50 words)"
    )
    source_location: str = Field(
        ...,
        description="Location in source document (e.g., 'abstract', 'keywords', 'solicitation')",
    )
    rationale_tag: str = Field(
        ...,
        description="Explanation of why this excerpt is relevant (e.g., 'Contains: quantum, computing')",
    )

    @field_validator("excerpt")
    @classmethod
    def validate_excerpt_length(cls, v: str) -> str:
        """Ensure excerpt is truncated to ~50 words."""
        words = v.split()
        if len(words) > 60:  # Allow slight buffer
            raise ValueError("Excerpt must be approximately 50 words or less")
        return v

    @field_validator("source_location")
    @classmethod
    def validate_source_location(cls, v: str) -> str:
        """Ensure source location is one of the expected values."""
        valid_locations = ["abstract", "keywords", "solicitation", "title", "description"]
        if v not in valid_locations:
            raise ValueError(f"Source location must be one of: {', '.join(valid_locations)}")
        return v


class CETClassification(BaseModel):
    """
    Classification result for a single CET area.

    Includes confidence score and classification level (High/Medium/Low).
    """

    cet_id: str = Field(..., description="CET area identifier")
    cet_name: str | None = Field(None, description="Human-readable CET area name")
    score: float = Field(..., ge=0.0, le=100.0, description="Confidence score (0-100)")
    classification: ClassificationLevel = Field(
        ..., description="Classification level (High/Medium/Low)"
    )
    primary: bool = Field(..., description="Whether this is the primary CET area (highest score)")
    evidence: list[EvidenceStatement] = Field(
        default_factory=list, description="Supporting evidence (up to 3 statements)"
    )
    classified_at: str | None = Field(None, description="ISO 8601 timestamp of classification")
    taxonomy_version: str | None = Field(None, description="Taxonomy version (e.g., 'NSTC-2025Q1')")

    @field_validator("evidence")
    @classmethod
    def validate_evidence_count(cls, v: list[EvidenceStatement]) -> list[EvidenceStatement]:
        """Limit evidence to top 3 most relevant statements."""
        if len(v) > 3:
            raise ValueError("Maximum 3 evidence statements allowed per classification")
        return v

    @field_validator("classification")
    @classmethod
    def validate_classification_matches_score(
        cls, v: ClassificationLevel, info
    ) -> ClassificationLevel:
        """Ensure classification level matches score thresholds."""
        score = info.data.get("score")
        if score is None:
            return v

        expected_level = (
            ClassificationLevel.HIGH
            if score >= 70
            else ClassificationLevel.MEDIUM
            if score >= 40
            else ClassificationLevel.LOW
        )

        if v != expected_level:
            raise ValueError(
                f"Classification {v} does not match score {score} (expected {expected_level})"
            )
        return v


class CETAssessment(BaseModel):
    """
    Complete CET assessment for an award, company, or patent.

    Combines primary and supporting CET classifications with metadata.
    """

    entity_id: str = Field(
        ..., description="ID of the entity being classified (award_id, company_id, patent_id)"
    )
    entity_type: str = Field(..., description="Type of entity ('award', 'company', 'patent')")
    primary_cet: CETClassification = Field(..., description="Primary CET area (highest confidence)")
    supporting_cets: list[CETClassification] = Field(
        default_factory=list, description="Supporting CET areas (up to 3)"
    )
    classified_at: datetime = Field(
        default_factory=datetime.utcnow, description="Timestamp of classification"
    )
    taxonomy_version: str = Field(..., description="Taxonomy version used (e.g., 'NSTC-2025Q1')")
    model_version: str = Field(..., description="Classifier model version (e.g., 'v1.0.0')")

    @field_validator("entity_type")
    @classmethod
    def validate_entity_type(cls, v: str) -> str:
        """Ensure entity type is valid."""
        valid_types = ["award", "company", "patent"]
        if v not in valid_types:
            raise ValueError(f"Entity type must be one of: {', '.join(valid_types)}")
        return v

    @field_validator("supporting_cets")
    @classmethod
    def validate_supporting_count(cls, v: list[CETClassification]) -> list[CETClassification]:
        """Limit supporting CETs to 3."""
        if len(v) > 3:
            raise ValueError("Maximum 3 supporting CET areas allowed")
        return v

    @field_validator("supporting_cets")
    @classmethod
    def validate_all_supporting(cls, v: list[CETClassification]) -> list[CETClassification]:
        """Ensure all supporting CETs have primary=False."""
        for cet in v:
            if cet.primary:
                raise ValueError("Supporting CETs must have primary=False")
        return v

    @field_validator("primary_cet")
    @classmethod
    def validate_primary_flag(cls, v: CETClassification) -> CETClassification:
        """Ensure primary CET has primary=True."""
        if not v.primary:
            raise ValueError("Primary CET must have primary=True")
        return v


class CompanyCETProfile(BaseModel):
    """
    Aggregated CET profile for a company across all awards.

    Tracks company specialization, evolution, and dominant technology areas.
    """

    company_id: str = Field(..., description="Company identifier")
    dominant_cet_id: str = Field(..., description="CET area with highest aggregated score")
    award_count: int = Field(..., ge=1, description="Number of awards in this CET area")
    total_funding: float = Field(..., ge=0.0, description="Total funding in this CET area")
    avg_score: float = Field(..., ge=0.0, le=100.0, description="Average classification score")
    specialization_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Concentration in dominant CET (0-1, higher = more specialized)",
    )
    dominant_phase: str | None = Field(
        None, description="Most common award phase in this CET (I, II, III)"
    )
    first_award_date: datetime | None = Field(
        None, description="Date of first award in this CET area"
    )
    last_award_date: datetime | None = Field(
        None, description="Date of most recent award in this CET area"
    )
    cet_areas: list[str] = Field(
        default_factory=list, description="All CET areas the company has worked in"
    )


class TrainingExample(BaseModel):
    """
    Labeled training example for CET classification model training.

    Used for supervised learning to train the ApplicabilityModel. Each example
    contains the text features used for classification and the ground truth labels.
    """

    example_id: str = Field(..., description="Unique identifier for this training example")
    text: str = Field(..., description="Text to classify (award abstract or combined fields)")
    title: str | None = Field(None, description="Award title (if available)")
    keywords: str | None = Field(None, description="Award keywords (if available)")
    solicitation: str | None = Field(None, description="Solicitation topic (if available)")
    labels: list[str] = Field(..., description="Ground truth CET IDs (one or more applicable CETs)")
    label_confidence: float | None = Field(
        None, ge=0.0, le=1.0, description="Confidence in labels (0-1, if provided by annotator)"
    )
    source: str = Field(
        ..., description="Source of the label (e.g., 'manual', 'bootstrap', 'expert')"
    )
    annotated_by: str | None = Field(None, description="Annotator ID or name")
    annotated_at: datetime | None = Field(None, description="Timestamp of annotation")
    notes: str | None = Field(None, description="Optional notes about this example")

    @field_validator("labels")
    @classmethod
    def validate_labels_not_empty(cls, v: list[str]) -> list[str]:
        """Ensure at least one label is provided."""
        if not v:
            raise ValueError("At least one label is required")
        return v

    @field_validator("text")
    @classmethod
    def validate_text_not_empty(cls, v: str) -> str:
        """Ensure text is not empty."""
        if not v.strip():
            raise ValueError("Text cannot be empty")
        return v


class TrainingDataset(BaseModel):
    """
    Collection of training examples with metadata.

    Represents a complete training dataset for model training and evaluation.
    """

    dataset_id: str = Field(..., description="Unique identifier for this dataset")
    examples: list[TrainingExample] = Field(..., description="Training examples")
    taxonomy_version: str = Field(..., description="CET taxonomy version (e.g., 'NSTC-2025Q1')")
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Dataset creation timestamp"
    )
    description: str | None = Field(None, description="Description of this dataset")
    split: str | None = Field(None, description="Dataset split (e.g., 'train', 'val', 'test')")

    @field_validator("examples")
    @classmethod
    def validate_examples_not_empty(cls, v: list[TrainingExample]) -> list[TrainingExample]:
        """Ensure dataset contains examples."""
        if not v:
            raise ValueError("Dataset must contain at least one example")
        return v

    def __len__(self) -> int:
        """Return number of examples in dataset."""
        return len(self.examples)


__all__ = [
    "ClassificationLevel",
    "CETArea",
    "EvidenceStatement",
    "CETClassification",
    "CETAssessment",
    "CompanyCETProfile",
    "TrainingExample",
    "TrainingDataset",
]
