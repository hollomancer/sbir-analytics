"""Helpers for OT consortium Dagster asset configuration.

The OT consortium assets accept local or mounted files for:

- the CMF consortium member registry; and
- optional external OT Phase III transition assertions.

Project configuration is the primary source for both paths. Environment
variables are intentionally treated as deployment-specific overrides.
"""

import os
from pathlib import Path

from sbir_etl.config import get_config
from sbir_etl.config.schemas import PipelineConfig


REGISTRY_PATH_ENV = "SBIR_ETL__OT_CONSORTIUM__CMF_REGISTRY_PATH"
TRANSITION_CLAIMS_PATH_ENV = "SBIR_ETL__OT_CONSORTIUM__TRANSITION_CLAIMS_PATH"
LEGACY_CLAIMS_PATH_ENV = "SBIR_ETL__OT_CONSORTIUM__CLAIMS_PATH"


def _resolve_configured_path(path: str | None) -> Path | None:
    """Resolve a configured path against the current project root."""
    if not path:
        return None

    expanded = Path(os.path.expanduser(os.path.expandvars(path)))
    if not expanded.is_absolute():
        expanded = Path.cwd() / expanded
    return expanded.resolve()


def cmf_registry_path(config: PipelineConfig | None = None) -> Path | None:
    """Return the CMF registry path.

    Environment overrides apply only when no ``config`` is injected. When a caller
    passes an explicit ``PipelineConfig`` it is authoritative — deterministic for
    tests and for callers that intentionally disable env overrides.
    """
    ot_config = (config or get_config()).ot_consortium
    env_override = os.getenv(REGISTRY_PATH_ENV) if config is None else None
    return _resolve_configured_path(env_override or ot_config.cmf_registry_path)


def transition_claims_path(config: PipelineConfig | None = None) -> Path | None:
    """Return the optional external OT Phase III assertions path.

    The preferred configuration key is ``transition_claims_path``. The legacy
    ``claims_path`` key and matching environment variable are still supported.
    Environment overrides apply only when no ``config`` is injected, so an explicit
    ``PipelineConfig`` is authoritative.
    """
    ot_config = (config or get_config()).ot_consortium
    env_override = (
        (os.getenv(TRANSITION_CLAIMS_PATH_ENV) or os.getenv(LEGACY_CLAIMS_PATH_ENV))
        if config is None
        else None
    )
    return _resolve_configured_path(env_override or ot_config.effective_transition_claims_path)
