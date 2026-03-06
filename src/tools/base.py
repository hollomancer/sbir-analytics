"""
Base tool infrastructure for SBIR analytics agent missions.

Every tool in the system returns a ToolResult with mandatory metadata for
provenance tracking, reproducibility, and audit trails. This module defines
the standard interface contract described in the mission specifications.

Key classes:
    - ToolResult: Standard return type for all tools
    - ToolMetadata: Provenance, timing, freshness — mandatory on every result
    - DataSourceRef: Reference to a specific public data source consumed
    - BaseTool: Abstract base class for all tool implementations
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd
from loguru import logger


@dataclass
class DataSourceRef:
    """Reference to a specific public data source consumed by a tool.

    Every tool must declare which public data sources it touched, enabling
    full audit trails from output claims → tool calls → data sources → records.

    Attributes:
        name: Human-readable source name (e.g., "SBIR.gov Awards", "FPDS-NG")
        url: Canonical URL for the data source
        version: Version or date stamp of the data snapshot used
        record_count: Number of records consumed from this source
        access_method: How the data was accessed (e.g., "bulk_download", "api", "parquet")
    """

    name: str
    url: str
    version: str | None = None
    record_count: int | None = None
    access_method: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "url": self.url,
            "version": self.version,
            "record_count": self.record_count,
            "access_method": self.access_method,
        }


@dataclass
class ToolMetadata:
    """Mandatory metadata attached to every tool result.

    Provides provenance, timing, and lineage information required for
    reproducibility and audit trails across multi-tool mission workflows.

    Attributes:
        tool_name: Identifier for the tool that produced this result
        tool_version: Semantic version of the tool implementation
        execution_start: When the tool began executing
        execution_end: When the tool finished (None if still running)
        data_sources: Public data sources consumed during execution
        parameters_used: Input parameters for reproducibility
        record_count: Number of records in the primary output
        warnings: Data quality issues or caveats discovered
        confidence: LLM judgment confidence (None for deterministic tools)
        upstream_tools: Tool names whose output was consumed as input
    """

    tool_name: str
    tool_version: str
    execution_start: datetime
    execution_end: datetime | None = None
    data_sources: list[DataSourceRef] = field(default_factory=list)
    parameters_used: dict[str, Any] = field(default_factory=dict)
    record_count: int = 0
    warnings: list[str] = field(default_factory=list)
    confidence: float | None = None
    upstream_tools: list[str] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float | None:
        if self.execution_start and self.execution_end:
            return (self.execution_end - self.execution_start).total_seconds()
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "tool_version": self.tool_version,
            "execution_start": self.execution_start.isoformat(),
            "execution_end": self.execution_end.isoformat() if self.execution_end else None,
            "duration_seconds": self.duration_seconds,
            "data_sources": [ds.to_dict() for ds in self.data_sources],
            "parameters_used": self.parameters_used,
            "record_count": self.record_count,
            "warnings": self.warnings,
            "confidence": self.confidence,
            "upstream_tools": self.upstream_tools,
        }


@dataclass
class ToolResult:
    """Standard return type for all agent tools.

    Every tool in the system returns a ToolResult containing the primary output
    data and mandatory metadata. The chain_metadata() method propagates provenance
    through multi-tool workflows.

    Attributes:
        data: Primary output — DataFrame for tabular results, dict for structured results
        metadata: Provenance, timing, freshness — mandatory
    """

    data: pd.DataFrame | dict[str, Any]
    metadata: ToolMetadata

    def chain_metadata(self, downstream_metadata: ToolMetadata) -> ToolMetadata:
        """Propagate provenance from this result into a downstream tool's metadata.

        When Mission C consumes Mission B's output, the data source chain traces
        all the way back to FPDS and SAM.gov through this mechanism.

        Args:
            downstream_metadata: The metadata object of the tool consuming this result

        Returns:
            The downstream metadata with upstream provenance appended
        """
        downstream_metadata.upstream_tools.append(self.metadata.tool_name)
        downstream_metadata.data_sources.extend(self.metadata.data_sources)
        return downstream_metadata

    def to_dict(self) -> dict[str, Any]:
        data_repr = self.data if isinstance(self.data, dict) else {
            "type": "DataFrame",
            "shape": list(self.data.shape),
            "columns": list(self.data.columns),
        }
        return {
            "data": data_repr,
            "metadata": self.metadata.to_dict(),
        }


class BaseTool(ABC):
    """Abstract base class for all SBIR analytics agent tools.

    Subclasses implement execute() with their specific logic. The run() method
    wraps execute() with timing, error handling, and metadata population.

    Attributes:
        name: Tool identifier (used in metadata and logging)
        version: Semantic version string
    """

    name: str = "base_tool"
    version: str = "0.1.0"

    def __init__(self, **kwargs: Any):
        self._config = kwargs

    def run(self, **kwargs: Any) -> ToolResult:
        """Execute the tool with automatic metadata tracking.

        This is the public entry point. It wraps execute() with:
        - Execution timing
        - Parameter capture for reproducibility
        - Error handling with metadata preservation

        Args:
            **kwargs: Tool-specific parameters passed to execute()

        Returns:
            ToolResult with data and populated metadata
        """
        metadata = ToolMetadata(
            tool_name=self.name,
            tool_version=self.version,
            execution_start=datetime.utcnow(),
            parameters_used=self._sanitize_params(kwargs),
        )

        logger.info(f"Tool '{self.name}' v{self.version} starting")
        start = time.monotonic()

        try:
            result = self.execute(metadata=metadata, **kwargs)
            metadata.execution_end = datetime.utcnow()
            elapsed = time.monotonic() - start
            logger.info(
                f"Tool '{self.name}' completed in {elapsed:.2f}s "
                f"({metadata.record_count} records)"
            )
            return result
        except Exception:
            metadata.execution_end = datetime.utcnow()
            logger.error(f"Tool '{self.name}' failed after {time.monotonic() - start:.2f}s")
            raise

    @abstractmethod
    def execute(self, metadata: ToolMetadata, **kwargs: Any) -> ToolResult:
        """Implement tool-specific logic.

        Subclasses must:
        1. Populate metadata.data_sources with consumed public data sources
        2. Set metadata.record_count
        3. Append any warnings to metadata.warnings
        4. Set metadata.confidence if LLM judgment was involved
        5. Return ToolResult(data=..., metadata=metadata)

        Args:
            metadata: Pre-initialized metadata to populate during execution
            **kwargs: Tool-specific parameters

        Returns:
            ToolResult with data and fully populated metadata
        """

    @staticmethod
    def _sanitize_params(params: dict[str, Any]) -> dict[str, Any]:
        """Remove non-serializable parameters for metadata storage."""
        sanitized = {}
        for k, v in params.items():
            if isinstance(v, pd.DataFrame):
                sanitized[k] = f"DataFrame(shape={v.shape})"
            elif isinstance(v, (str, int, float, bool, type(None))):
                sanitized[k] = v
            elif isinstance(v, (list, tuple)):
                sanitized[k] = [str(item) if not isinstance(item, (str, int, float, bool, type(None))) else item for item in v]
            elif isinstance(v, dict):
                sanitized[k] = str(v)[:200]
            else:
                sanitized[k] = str(type(v).__name__)
        return sanitized
