# sbir-etl/src/transition/__init__.py
"""
Transition detection package.

This module exposes basic configuration helpers and package-level constants for the
transition detection feature. It provides a small, robust `Config` container and a
`load_config` helper that will attempt to read a YAML configuration from the
repository `config/transition` directory, falling back to sensible defaults and
environment variable overrides.

Design goals:
- Lightweight and dependency-tolerant: works without YAML or Pydantic installed.
- Provides explicit defaults for rapid prototyping and CI runs.
- Central place to discover transition-related config keys and defaults.
"""

from __future__ import annotations

import dataclasses
import os
from typing import Any

from loguru import logger

from .evaluation.evaluator import ConfusionMatrix, EvaluationResult, TransitionEvaluator


# Package version: bumped manually when making releases for the transition module.
__version__ = "0.1.0"

DEFAULT_CONFIG_PATH = os.environ.get(
    "SBIR_TRANSITION_CONFIG",
    os.path.join("config", "transition", "detection.yaml"),
)

# Default values for the transition detection subsystem. These are intentionally
# conservative; operational teams should override them in `config/transition/*.yaml`
# or via environment variables in production.
DEFAULTS: dict[str, Any] = {
    "fuzzy_threshold": 0.90,  # vendor name fuzzy match threshold (0.0-1.0)
    "fuzzy_secondary_threshold": 0.80,  # lower-confidence threshold
    "batch_size_contracts": 100000,  # chunk size when scanning large contract datasets
    "detection_timing_window_months": 24,  # default window for transition detection
    "scoring": {
        "base_score": 0.15,
        "agency_same": 0.25,
        "agency_cross_service": 0.125,
        "timing_0_3": 1.0,
        "timing_3_12": 0.75,
        "timing_12_24": 0.5,
        "competition_sole": 0.20,
        "competition_limited": 0.10,
        "patent_has": 0.05,
        "patent_pre_contract": 0.03,
        "patent_topic_match": 0.02,
        "cet_alignment": 0.05,
        "text_similarity_weight": 0.05,
    },
    "vendor_matching": {
        "prefer_identifiers": True,
        "uei_priority": 0.99,
        "cage_priority": 0.95,
        "duns_priority": 0.90,
    },
    "metrics": {
        "emit_to": "artifacts/metrics",  # directory or metrics sink name
    },
}


@dataclasses.dataclass
class Config:
    """
    Lightweight configuration container for transition detection.

    Fields documented reflect the defaults above. Additional keys found in a
    configuration YAML will be preserved in the `extra` dict for downstream
    modules to consume.
    """

    fuzzy_threshold: float = DEFAULTS["fuzzy_threshold"]
    fuzzy_secondary_threshold: float = DEFAULTS["fuzzy_secondary_threshold"]
    batch_size_contracts: int = DEFAULTS["batch_size_contracts"]
    detection_timing_window_months: int = DEFAULTS["detection_timing_window_months"]
    scoring: dict[str, Any] = dataclasses.field(default_factory=lambda: dict(DEFAULTS["scoring"]))
    vendor_matching: dict[str, Any] = dataclasses.field(
        default_factory=lambda: dict(DEFAULTS["vendor_matching"])
    )
    metrics: dict[str, Any] = dataclasses.field(default_factory=lambda: dict(DEFAULTS["metrics"]))
    extra: dict[str, Any] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        return d


def _load_yaml(path: str) -> dict[str, Any] | None:
    """
    Minimal YAML loader that attempts to use a YAML library if available.

    Falls back to None if YAML parsing is not available or the file cannot be read.
    """
    try:
        import yaml
    except Exception:
        return None

    try:
        with open(path, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:
        return None


def _apply_overrides_from_env(cfg: dict[str, Any]) -> dict[str, Any]:
    """
    Apply environment variable overrides for a few common keys. This is lightweight
    and only supports simple scalar overrides. Consumers can extend this logic.
    """
    # Top-level scalar overrides
    env_map = {
        "SBIR_TRANSITION_FUZZY_THRESHOLD": ("fuzzy_threshold", float),
        "SBIR_TRANSITION_BATCH_SIZE": ("batch_size_contracts", int),
        "SBIR_TRANSITION_WINDOW_MONTHS": ("detection_timing_window_months", int),
    }
    for env_k, (cfg_k, cast) in env_map.items():
        val = os.environ.get(env_k)
        if val is not None:
            try:
                cfg[cfg_k] = cast(val)
            except Exception:
                # ignore invalid environment overrides
                pass
    return cfg


def load_config(path: str | None = None) -> Config:
    """
    Load transition detection configuration.

    Precedence:
      1. YAML file at the provided path (or DEFAULT_CONFIG_PATH)
      2. Environment variable overrides
      3. Defaults

    Returns a Config dataclass instance.
    """
    cfg_path = path or DEFAULT_CONFIG_PATH
    loaded: dict[str, Any] = {}

    # Attempt to load YAML if available
    yaml_data = _load_yaml(cfg_path)
    if yaml_data:
        loaded.update(yaml_data)

    # Apply environment overrides conservatively
    loaded = _apply_overrides_from_env(loaded)

    # Merge loaded values into a Config instance using defaults for missing keys.
    cfg = Config()

    # Top-level simple fields
    if "fuzzy_threshold" in loaded:
        try:
            cfg.fuzzy_threshold = float(loaded["fuzzy_threshold"])
        except Exception:
            pass
    if "fuzzy_secondary_threshold" in loaded:
        try:
            cfg.fuzzy_secondary_threshold = float(loaded["fuzzy_secondary_threshold"])
        except Exception:
            pass
    if "batch_size_contracts" in loaded:
        try:
            cfg.batch_size_contracts = int(loaded["batch_size_contracts"])
        except Exception:
            pass
    if "detection_timing_window_months" in loaded:
        try:
            cfg.detection_timing_window_months = int(loaded["detection_timing_window_months"])
        except Exception:
            pass

    # dict fields
    for k in ("scoring", "vendor_matching", "metrics"):
        if k in loaded and isinstance(loaded[k], dict):
            getattr(cfg, k).update(loaded[k])

    # preserve any other keys as extra
    extra_keys = {
        k: v
        for k, v in loaded.items()
        if k
        not in {
            "fuzzy_threshold",
            "fuzzy_secondary_threshold",
            "batch_size_contracts",
            "detection_timing_window_months",
            "scoring",
            "vendor_matching",
            "metrics",
        }
    }
    cfg.extra.update(extra_keys)

    return cfg


# Convenience module-level config for quick imports
try:
    _MODULE_CONFIG = load_config()
except Exception:
    # Avoid failing import if config parsing fails; fall back to defaults
    logger.debug("Failed to load transition config at import time; using defaults.")
    _MODULE_CONFIG = Config()


def get_config() -> Config:
    """
    Return the module-level loaded Config object. Callers that need to re-load from
    a different path should call `load_config(path)` explicitly.
    """
    return _MODULE_CONFIG


__all__ = [
    "Config",
    "load_config",
    "get_config",
    "DEFAULT_CONFIG_PATH",
    "__version__",
    "ConfusionMatrix",
    "EvaluationResult",
    "TransitionEvaluator",
]
