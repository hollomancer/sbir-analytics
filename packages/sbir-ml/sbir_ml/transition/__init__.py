# sbir-analytics/src/transition/__init__.py
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
        "require_match": True,
    },
    "confidence_thresholds": {
        "high": 0.85,
        "likely": 0.65,
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
    confidence_thresholds: dict[str, float] = dataclasses.field(
        default_factory=lambda: dict(DEFAULTS["confidence_thresholds"])
    )
    metrics: dict[str, Any] = dataclasses.field(default_factory=lambda: dict(DEFAULTS["metrics"]))
    extra: dict[str, Any] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def to_detector_config(self) -> dict[str, Any]:
        """Build the config dict expected by TransitionDetector and TransitionScorer.

        Maps from this flat/grouped Config into the nested structure the
        detector pipeline reads at runtime, ensuring all thresholds come from
        one source of truth.
        """
        s = self.scoring
        return {
            "base_score": s.get("base_score", 0.15),
            "timing_window": {
                "min_days_after_completion": 0,
                "max_days_after_completion": round(
                    self.detection_timing_window_months * 365.25 / 12
                ),
            },
            "vendor_matching": {
                "require_match": self.vendor_matching.get("require_match", True),
                "prefer_identifiers": self.vendor_matching.get("prefer_identifiers", True),
                "fuzzy_threshold": self.fuzzy_threshold,
                "fuzzy_secondary_threshold": self.fuzzy_secondary_threshold,
            },
            "scoring": {
                "agency_continuity": {
                    "enabled": True,
                    "weight": 0.25,
                    "same_agency_bonus": s.get("agency_same", 0.25),
                    "cross_service_bonus": s.get("agency_cross_service", 0.125),
                    "different_dept_bonus": 0.05,
                },
                "timing_proximity": {
                    "enabled": True,
                    "weight": 0.20,
                    "windows": [
                        {"range": [0, 90], "score": s.get("timing_0_3", 1.0)},
                        {"range": [91, 365], "score": s.get("timing_3_12", 0.75)},
                        {"range": [366, 730], "score": s.get("timing_12_24", 0.5)},
                    ],
                    "beyond_window_penalty": 0.0,
                },
                "competition_type": {
                    "enabled": True,
                    "weight": 0.20,
                    "sole_source_bonus": s.get("competition_sole", 0.20),
                    "limited_competition_bonus": s.get("competition_limited", 0.10),
                    "full_and_open_bonus": 0.0,
                },
                "patent_signal": {
                    "enabled": True,
                    "weight": 0.15,
                    "has_patent_bonus": s.get("patent_has", 0.05),
                    "patent_pre_contract_bonus": s.get("patent_pre_contract", 0.03),
                    "patent_topic_match_bonus": s.get("patent_topic_match", 0.02),
                    "patent_similarity_threshold": 0.7,
                },
                "cet_alignment": {
                    "enabled": True,
                    "weight": 0.10,
                    "same_cet_area_bonus": s.get("cet_alignment", 0.05),
                },
                "text_similarity": {
                    "enabled": False,
                    "weight": s.get("text_similarity_weight", 0.05),
                },
            },
            "confidence_thresholds": {
                "high": self.confidence_thresholds.get("high", 0.85),
                "likely": self.confidence_thresholds.get("likely", 0.65),
            },
        }


def _load_yaml(path: str) -> dict[str, Any] | None:
    """
    Minimal YAML loader that attempts to use a YAML library if available.

    Falls back to None if YAML parsing is not available or the file cannot be read.
    """
    try:
        import yaml
    except ImportError:
        logger.debug("PyYAML not installed; skipping YAML config loading")
        return None

    try:
        with open(path, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except FileNotFoundError:
        logger.debug("Transition config file not found: {}", path)
        return None
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("Failed to load transition config from {}: {}", path, exc)
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
            except (ValueError, TypeError) as exc:
                logger.warning(
                    "Invalid environment override {}={!r} for {}: {}", env_k, val, cfg_k, exc
                )
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
    _scalar_fields: list[tuple[str, type, str]] = [
        ("fuzzy_threshold", float, "fuzzy_threshold"),
        ("fuzzy_secondary_threshold", float, "fuzzy_secondary_threshold"),
        ("batch_size_contracts", int, "batch_size_contracts"),
        ("detection_timing_window_months", int, "detection_timing_window_months"),
    ]
    for key, cast, attr in _scalar_fields:
        if key in loaded:
            try:
                setattr(cfg, attr, cast(loaded[key]))
            except (ValueError, TypeError) as exc:
                logger.warning("Invalid config value {}={!r}: {}", key, loaded[key], exc)

    # dict fields
    for k in ("scoring", "vendor_matching", "confidence_thresholds", "metrics"):
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
except (OSError, ValueError, TypeError) as _load_exc:
    logger.warning("Failed to load transition config at import time: {}; using defaults.", _load_exc)
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
