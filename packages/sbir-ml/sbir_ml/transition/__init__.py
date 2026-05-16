"""Transition detection package.

Exposes the lightweight `Config` dataclass that translates transition scoring
weights and thresholds into the nested config dict the
`TransitionDetector`/`TransitionScorer` pipeline reads at runtime.

Submodules:
- `detection/` — detector pipeline, scoring, evidence generation
- `evaluation/` — quality metrics for detected transitions
- `features/` — vendor resolution, crosswalks
- `analysis/` — post-detection analytics
"""

from __future__ import annotations

import dataclasses
from typing import Any

from .evaluation.evaluator import ConfusionMatrix, EvaluationResult, TransitionEvaluator


__version__ = "0.1.0"

# Default scoring weights / thresholds for transition detection. These are
# conservative; operational teams should override via the detector pipeline's
# config (loaded by `load_yaml_config("config/transition/detection.yaml")`)
# rather than this dataclass.
DEFAULTS: dict[str, Any] = {
    "fuzzy_threshold": 0.90,
    "fuzzy_secondary_threshold": 0.80,
    "batch_size_contracts": 100000,
    "detection_timing_window_months": 24,
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
        "emit_to": "artifacts/metrics",
    },
}


@dataclasses.dataclass
class Config:
    """Lightweight configuration container for transition detection."""

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

        Maps this flat/grouped Config into the nested structure the detector
        pipeline reads at runtime so all thresholds come from one source.
        """
        s = self.scoring
        window_days = round(self.detection_timing_window_months * 365.25 / 12)
        return {
            "base_score": s.get("base_score", 0.15),
            "timing_window": {
                "min_days_after_completion": 0,
                "max_days_after_completion": window_days,
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


__all__ = [
    "Config",
    "ConfusionMatrix",
    "EvaluationResult",
    "TransitionEvaluator",
    "__version__",
]
