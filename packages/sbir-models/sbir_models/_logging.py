"""Logging compatibility shim for standalone sbir-models package.

Uses loguru if available (matching the full sbir_etl environment),
falls back to stdlib logging for standalone installations.
"""

from __future__ import annotations

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger("sbir_models")  # type: ignore[assignment]
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
