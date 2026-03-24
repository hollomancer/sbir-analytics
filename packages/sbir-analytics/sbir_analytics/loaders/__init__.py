"""Data loading modules.

Neo4j loaders are available when the ``neo4j`` extra is installed::

    pip install sbir-etl[neo4j]
"""

from __future__ import annotations

from typing import Any


__all__ = ["Neo4jClient", "Neo4jConfig", "LoadMetrics", "PatentLoader", "PatentLoaderConfig"]

_NEO4J_NAMES = {
    "LoadMetrics", "Neo4jClient", "Neo4jConfig", "PatentLoader", "PatentLoaderConfig",
}


def __getattr__(name: str) -> Any:
    if name in _NEO4J_NAMES:
        from . import neo4j as _neo4j  # noqa: F811

        return getattr(_neo4j, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
