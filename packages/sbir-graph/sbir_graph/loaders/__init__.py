"""Data loading modules.

Epistemic tier: pipelines. Loaders move validated records into Neo4j with
deterministic MERGE semantics; correctness is faithfulness to the input
records, and no loader performs inference or scoring.

Neo4j loaders are available after installing the repository workspace::

    make install
"""

from __future__ import annotations

from typing import Any


EPISTEMIC_TIER = "pipelines"

__all__ = [
    "EPISTEMIC_TIER",
    "Neo4jClient",
    "Neo4jConfig",
    "LoadMetrics",
    "PatentLoader",
    "PatentLoaderConfig",
]

_NEO4J_NAMES = {
    "LoadMetrics",
    "Neo4jClient",
    "Neo4jConfig",
    "PatentLoader",
    "PatentLoaderConfig",
}


def __getattr__(name: str) -> Any:
    if name in _NEO4J_NAMES:
        from . import neo4j as _neo4j  # noqa: F811

        return getattr(_neo4j, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
