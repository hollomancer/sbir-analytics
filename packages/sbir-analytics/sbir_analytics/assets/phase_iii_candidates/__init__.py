"""Phase III candidate-surfacing assets.

See ``specs/phase-3-solicitation-alerts/`` for the surfacing pipeline that
emits ``data/processed/phase_iii_candidates.parquet``. v1 ships the
RETROSPECTIVE, DIRECTED, and competitive FOLLOWON signal classes.
"""

from .assets import (
    CANDIDATES_OUTPUT_PATH,
    EVIDENCE_OUTPUT_PATH,
    HIGH_THRESHOLD_RETROSPECTIVE,
    HIGH_THRESHOLD_DIRECTED,
    HIGH_THRESHOLD_FOLLOWON,
    WEIGHTS_DIRECTED,
    WEIGHTS_FOLLOWON,
    WEIGHTS_RETROSPECTIVE,
    build_candidate_asset,
    phase_iii_retrospective_candidates,
    phase_iii_directed_candidates,
    phase_iii_followon_candidates,
)


__all__ = [
    "CANDIDATES_OUTPUT_PATH",
    "EVIDENCE_OUTPUT_PATH",
    "HIGH_THRESHOLD_RETROSPECTIVE",
    "HIGH_THRESHOLD_DIRECTED",
    "HIGH_THRESHOLD_FOLLOWON",
    "WEIGHTS_DIRECTED",
    "WEIGHTS_FOLLOWON",
    "WEIGHTS_RETROSPECTIVE",
    "build_candidate_asset",
    "phase_iii_retrospective_candidates",
    "phase_iii_directed_candidates",
    "phase_iii_followon_candidates",
]
