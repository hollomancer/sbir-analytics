"""Phase III candidate-surfacing assets.

Epistemic tier: exploratory. Candidate surfacing ranks pairs with
hand-weighted similarity and thresholds (an experimental lift per
``specs/phase3-candidate-enrichment``, not production), so candidates are
non-citable; deterministic pair construction in ``pairing`` declares
pipelines per-file.

See ``specs/phase-3-solicitation-alerts/`` for the surfacing pipeline that
emits ``data/processed/phase_iii_candidates.parquet``. v1 ships the
RETROSPECTIVE, DIRECTED, and competitive FOLLOWON signal classes.
"""

EPISTEMIC_TIER = "exploratory"

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
    "candidates_path_for",
    "combine_candidate_outputs",
    "enrich_prior_awards",
    "evidence_path_for",
    "phase_iii_candidates",
    "phase_iii_retrospective_candidates",
    "phase_iii_directed_candidates",
    "phase_iii_followon_candidates",
]


def __getattr__(name: str):
    """Load the weighted scoring surface only when explicitly requested.

    Importing the neutral ``pairing`` submodule must not import the scorer or
    weight constants as a package-initialization side effect. All current
    package-level exports remain available lazily for compatibility.
    """

    if name not in __all__:
        raise AttributeError(name)

    import importlib

    assets_module = importlib.import_module(f"{__name__}.assets")
    return getattr(assets_module, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
