"""
Neo4j loaders package for SBIR graph database operations.

This package contains modularized Neo4j loaders for loading various data types
into the Neo4j graph database, including patents, CET classifications, transitions,
profiles, and company categorizations.

Module Structure:
- client: Base Neo4j client for batch operations and transaction management
- patents: Patent assignment loader (USPTO data)
- patent_cet: Patent CET classification loader
- cet: CET taxonomy and enrichment loader
- transitions: Transition detection loader
- profiles: Transition profile loader
- categorization: Company categorization loader (Product/Service/Mixed)

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
- CompanyCategorizationLoader: Loader for company categorizations
- CompanyCategorizationLoaderConfig: Configuration for categorization loading
"""

from __future__ import annotations

# Base module
from .base import BaseNeo4jLoader

# Categorization module (company Product/Service/Mixed classification)
from .categorization import CompanyCategorizationLoader, CompanyCategorizationLoaderConfig

# CET module
from .cet import CETLoader, CETLoaderConfig

# Client module
from .client import LoadMetrics, Neo4jClient, Neo4jConfig

# Patent CET module (patent classifications)
from .patent_cet import Neo4jPatentCETLoader

# Patents module (USPTO assignments)
from .patents import PatentLoader, PatentLoaderConfig

# Profiles module
from .profiles import TransitionProfileLoader

# Transitions module
from .transitions import TransitionLoader

# Organizations module
from .organizations import OrganizationLoader


__all__ = [
    # Base
    "BaseNeo4jLoader",
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
    # Categorization (Product/Service/Mixed)
    "CompanyCategorizationLoader",
    "CompanyCategorizationLoaderConfig",
    # Organizations
    "OrganizationLoader",
]
