"""Phase III candidate-surfacing assets.

See ``specs/phase-3-solicitation-alerts/`` for the surfacing pipeline that
emits ``data/processed/phase_iii_candidates.parquet``. v1 ships the
RETROSPECTIVE signal (Phase III contracts not coded as such in FPDS); the
DIRECTED and FOLLOWON classes will land in subsequent phases.
"""

from .assets import (
    CANDIDATES_OUTPUT_PATH,
    EVIDENCE_OUTPUT_PATH,
    HIGH_THRESHOLD_RETROSPECTIVE,
    WEIGHTS_RETROSPECTIVE,
    build_candidate_asset,
    phase_iii_retrospective_candidates,
)


__all__ = [
    "CANDIDATES_OUTPUT_PATH",
    "EVIDENCE_OUTPUT_PATH",
    "HIGH_THRESHOLD_RETROSPECTIVE",
    "WEIGHTS_RETROSPECTIVE",
    "build_candidate_asset",
    "phase_iii_retrospective_candidates",
]
