"""
Neo4j loaders package for SBIR graph database operations.

This package requires the ``neo4j`` optional dependency.  Install it with::

    pip install sbir-graph

All public symbols are lazily imported so that the rest of the ``sbir_etl``
package can be imported without neo4j being installed.
"""

from __future__ import annotations

from typing import Any


__all__ = [
    # Base
    "BaseLoaderConfig",
    "BaseNeo4jLoader",
    # Client
    "Neo4jClient",
    "Neo4jConfig",
    "Neo4jHealthStatus",
    "Neo4jStatistics",
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
    # SEC EDGAR
    "SecEdgarLoader",
    "SecEdgarLoaderConfig",
]

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "BaseLoaderConfig": (".base", "BaseLoaderConfig"),
    "BaseNeo4jLoader": (".base", "BaseNeo4jLoader"),
    "CompanyCategorizationLoader": (".categorization", "CompanyCategorizationLoader"),
    "CompanyCategorizationLoaderConfig": (".categorization", "CompanyCategorizationLoaderConfig"),
    "CETLoader": (".cet", "CETLoader"),
    "CETLoaderConfig": (".cet", "CETLoaderConfig"),
    "LoadMetrics": (".client", "LoadMetrics"),
    "Neo4jClient": (".client", "Neo4jClient"),
    "Neo4jConfig": (".client", "Neo4jConfig"),
    "Neo4jHealthStatus": (".client", "Neo4jHealthStatus"),
    "Neo4jStatistics": (".client", "Neo4jStatistics"),
    "OrganizationLoader": (".organizations", "OrganizationLoader"),
    "SecEdgarLoader": (".sec_edgar", "SecEdgarLoader"),
    "SecEdgarLoaderConfig": (".sec_edgar", "SecEdgarLoaderConfig"),
    "Neo4jPatentCETLoader": (".patent_cet", "Neo4jPatentCETLoader"),
    "PatentLoader": (".patents", "PatentLoader"),
    "PatentLoaderConfig": (".patents", "PatentLoaderConfig"),
    "TransitionProfileLoader": (".profiles", "TransitionProfileLoader"),
    "TransitionLoader": (".transitions", "TransitionLoader"),
}


def __getattr__(name: str) -> Any:
    if name in _LAZY_IMPORTS:
        rel_module, attr = _LAZY_IMPORTS[name]
        try:
            from importlib import import_module

            mod = import_module(rel_module, __name__)
        except ImportError as exc:
            raise ImportError(
                f"The neo4j package is required to use {name}. "
                "Install it with: pip install sbir-graph"
            ) from exc
        value = getattr(mod, attr)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(list(__all__) + list(globals().keys()))
