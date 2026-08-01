"""Phase III candidate-surfacing assets.

See ``specs/phase-3-solicitation-alerts/`` for the surfacing pipeline that
emits ``data/processed/phase_iii_candidates.parquet``. v1 ships the
RETROSPECTIVE signal (Phase III contracts not coded as such in FPDS); the
DIRECTED and FOLLOWON classes will land in subsequent phases.
"""

__all__ = [
    "CANDIDATES_OUTPUT_PATH",
    "EVIDENCE_OUTPUT_PATH",
    "HIGH_THRESHOLD_RETROSPECTIVE",
    "WEIGHTS_RETROSPECTIVE",
    "build_candidate_asset",
    "phase_iii_retrospective_candidates",
]


def __getattr__(name: str):
    """Load the legacy scoring surface only when a caller explicitly requests it.

    Importing the neutral ``pairing`` submodule must not import the scorer or its
    weights as a package-initialization side effect. Existing package-level imports
    remain available lazily for compatibility.
    """

    if name not in __all__:
        raise AttributeError(name)
    import importlib

    assets_module = importlib.import_module(f"{__name__}.assets")
    return getattr(assets_module, name)
