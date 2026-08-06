"""Quality utilities for SBIR ETL.

Epistemic tier: pipelines. Quality checks, baselines, and study-manifest
handling are deterministic gates over declared inputs; they infer nothing.

Submodules: uspto_validators, baseline, dashboard, checks.
"""

from .uspto_validators import USPTODataQualityValidator, USPTOValidationConfig


EPISTEMIC_TIER = "pipelines"


__all__ = ["USPTODataQualityValidator", "USPTOValidationConfig"]
