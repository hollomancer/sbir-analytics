"""
Agent tools for SBIR analytics missions.

This package provides the tool layer that agents use to accomplish mission goals.
Each tool wraps existing pipeline modules (extractors, enrichers, transformers, loaders)
behind a standard interface with provenance tracking, metadata, and audit trails.

Architecture:
    Agents own goals. Tools own operations. Dagster owns execution.
    LLM judgment enters only at genuine decision points — not data movement.

Build sequence (by dependency, not importance):
    Phase 0: Foundation (SAM, FPDS, entity resolution)
    Mission A: Portfolio Analysis (topics, clusters, gaps, metrics)
    Mission B: Benchmarks (transition rate, observable commercialization)
    Mission C: Fiscal Returns (tax estimation, crosswalk wrappers)
"""

from .base import BaseTool, DataSourceRef, ToolMetadata, ToolResult

__all__ = [
    "BaseTool",
    "DataSourceRef",
    "ToolMetadata",
    "ToolResult",
]
