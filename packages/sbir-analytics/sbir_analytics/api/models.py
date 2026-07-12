"""Public response models for the private analytics API."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class Provenance(BaseModel):
    """Metadata needed to reproduce and qualify an analytical result."""

    as_of: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source: str = "neo4j"
    methodology_version: str = "v1"
    pipeline_run_id: str | None = None
    limitations: list[str] = Field(default_factory=list)


class Page(BaseModel):
    limit: int
    offset: int
    returned: int


class AnalyticsResponse(BaseModel):
    data: list[dict[str, Any]]
    provenance: Provenance
    page: Page | None = None


class HealthResponse(BaseModel):
    status: str
    service: str = "sbir-analytics-api"


class ReadinessResponse(HealthResponse):
    components: dict[str, str]
