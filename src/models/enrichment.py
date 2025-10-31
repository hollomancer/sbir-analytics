"""Enrichment freshness tracking models.

This module provides data structures for tracking enrichment freshness,
delta detection, and state management for iterative API refresh workflows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EnrichmentStatus(str, Enum):
    """Status of an enrichment operation."""

    SUCCESS = "success"
    FAILED = "failed"
    UNCHANGED = "unchanged"
    STALE = "stale"
    PENDING = "pending"
    SKIPPED = "skipped"


@dataclass
class EnrichmentFreshnessRecord:
    """Record tracking freshness metadata for a single award-source pair.
    
    Tracks when enrichment was last attempted, last succeeded, payload changes,
    and current status to support iterative refresh workflows.
    """

    award_id: str
    source: str  # e.g., "usaspending"
    last_attempt_at: datetime
    last_success_at: datetime | None = None
    payload_hash: str | None = None  # SHA256 of API response JSON
    status: EnrichmentStatus = EnrichmentStatus.PENDING
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)  # e.g., modification_number, action_date
    attempt_count: int = 0
    success_count: int = 0

    def is_stale(self, sla_days: int) -> bool:
        """Check if this record is stale based on SLA.
        
        Args:
            sla_days: Maximum allowed age in days
            
        Returns:
            True if record exceeds SLA staleness threshold
        """
        if self.last_success_at is None:
            return True
        
        age_days = (datetime.now() - self.last_success_at).total_seconds() / 86400
        return age_days > sla_days

    def has_delta(self, new_payload_hash: str) -> bool:
        """Check if new payload differs from stored hash.
        
        Args:
            new_payload_hash: Hash of new API response
            
        Returns:
            True if payload has changed
        """
        if self.payload_hash is None:
            return True  # No previous hash means we consider it a delta
        
        return self.payload_hash != new_payload_hash


class EnrichmentFreshnessRecordModel(BaseModel):
    """Pydantic model for EnrichmentFreshnessRecord serialization.
    
    Used for JSON/Parquet persistence and validation.
    """

    award_id: str = Field(..., description="SBIR award identifier")
    source: str = Field(..., description="Enrichment source name (e.g., 'usaspending')")
    last_attempt_at: datetime = Field(..., description="Timestamp of last enrichment attempt")
    last_success_at: datetime | None = Field(
        None, description="Timestamp of last successful enrichment"
    )
    payload_hash: str | None = Field(
        None, description="SHA256 hash of last successful API response payload"
    )
    status: str = Field(
        default=EnrichmentStatus.PENDING.value,
        description="Current enrichment status",
    )
    error_message: str | None = Field(None, description="Error message if enrichment failed")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Source-specific metadata (modification_number, action_date, etc.)",
    )
    attempt_count: int = Field(default=0, description="Total number of enrichment attempts")
    success_count: int = Field(default=0, description="Total number of successful enrichments")

    model_config = ConfigDict(
        validate_assignment=True,
        json_encoders={datetime: lambda v: v.isoformat()},
    )

    @classmethod
    def from_dataclass(cls, record: EnrichmentFreshnessRecord) -> EnrichmentFreshnessRecordModel:
        """Convert dataclass instance to Pydantic model."""
        return cls(
            award_id=record.award_id,
            source=record.source,
            last_attempt_at=record.last_attempt_at,
            last_success_at=record.last_success_at,
            payload_hash=record.payload_hash,
            status=record.status.value if isinstance(record.status, EnrichmentStatus) else record.status,
            error_message=record.error_message,
            metadata=record.metadata,
            attempt_count=record.attempt_count,
            success_count=record.success_count,
        )

    def to_dataclass(self) -> EnrichmentFreshnessRecord:
        """Convert Pydantic model to dataclass instance."""
        return EnrichmentFreshnessRecord(
            award_id=self.award_id,
            source=self.source,
            last_attempt_at=self.last_attempt_at,
            last_success_at=self.last_success_at,
            payload_hash=self.payload_hash,
            status=EnrichmentStatus(self.status),
            error_message=self.error_message,
            metadata=self.metadata,
            attempt_count=self.attempt_count,
            success_count=self.success_count,
        )


class EnrichmentDeltaEvent(BaseModel):
    """Event emitted when enrichment payload changes.
    
    Used to notify downstream consumers of enrichment updates.
    """

    award_id: str = Field(..., description="SBIR award identifier")
    source: str = Field(..., description="Enrichment source name")
    timestamp: datetime = Field(default_factory=datetime.now, description="When delta was detected")
    old_payload_hash: str | None = Field(None, description="Previous payload hash")
    new_payload_hash: str = Field(..., description="New payload hash")
    changed_fields: list[str] = Field(
        default_factory=list, description="List of fields that changed"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional delta metadata"
    )

    model_config = ConfigDict(
        validate_assignment=True,
        json_encoders={datetime: lambda v: v.isoformat()},
    )
