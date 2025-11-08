"""
Neo4j loaders package for SBIR graph database operations.

This package contains modularized Neo4j loaders for loading various data types
into the Neo4j graph database, including patents, CET classifications, transitions,
and profiles.

Module Structure:
- client: Base Neo4j client for batch operations and transaction management
- patents: Patent assignment loader (USPTO data)
- patent_cet: Patent CET classification loader
- cet: CET taxonomy and enrichment loader
- transitions: Transition detection loader
- profiles: Transition profile loader

Pipeline Usage:
1. Client: Establish Neo4j connection and manage transactions
2. Loaders: Load specific data types (patents, CET, transitions, etc.)
3. Each loader uses the client for batch operations and idempotent merges

Exported Classes:
- Neo4jClient: Base client for Neo4j operations
- Neo4jConfig: Configuration for Neo4j connection
- LoadMetrics: Metrics tracking for load operations
- PatentLoader: Loader for patent assignments
- PatentLoaderConfig: Configuration for patent loading
- Neo4jPatentCETLoader: Loader for patent CET classifications
- CETLoader: Loader for CET taxonomy and enrichment
- CETLoaderConfig: Configuration for CET loading
- TransitionLoader: Loader for transition detections
- TransitionProfileLoader: Loader for transition profiles
"""

from __future__ import annotations

# Client module
from .client import (
    LoadMetrics,
    Neo4jClient,
    Neo4jConfig,
)

# Patents module (USPTO assignments)
from .patents import (
    PatentLoader,
    PatentLoaderConfig,
)

# Patent CET module (patent classifications)
from .patent_cet import (
    Neo4jPatentCETLoader,
)

# CET module
from .cet import (
    CETLoader,
    CETLoaderConfig,
)

# Transitions module
from .transitions import (
    TransitionLoader,
)

# Profiles module
from .profiles import (
    TransitionProfileLoader,
)


__all__ = [
    # Client
    "Neo4jClient",
    "Neo4jConfig",
    "LoadMetrics",
    # Patents (USPTO assignments)
    "PatentLoader",
    "PatentLoaderConfig",
    # Patent CET (classifications)
    "Neo4jPatentCETLoader",
    # CET
    "CETLoader",
    "CETLoaderConfig",
    # Transitions
    "TransitionLoader",
    # Profiles
    "TransitionProfileLoader",
]
