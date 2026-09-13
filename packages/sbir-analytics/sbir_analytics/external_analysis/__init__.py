"""Provider-neutral external analysis: freeze a study bundle, run it, import results.

Epistemic tier: exploratory. The study contract stays in ``studies/<id>/study.yaml``.
A provider is an execution backend. Returned artifacts are always
``evidence_status: exploratory`` and ``citable: false``; they cannot promote
themselves.

This package is not imported by Dagster definitions or the asset graph.
"""

from .base import ExternalAnalysisProvider, get_provider, run_external_analysis
from .bundle import freeze_study_bundle
from .models import (
    EdisonSupportNotInstalled,
    ExternalAnalysisError,
    ExternalAnalysisRun,
    ExternalUploadNotAuthorized,
    HashMismatchError,
    InvalidProviderResponse,
    MissingApiKey,
    MissingInputError,
    PromotionAttemptError,
    ProviderFailure,
    StudyBundle,
    StudyBundleManifest,
    UnsafeUploadError,
)


EPISTEMIC_TIER = "exploratory"

__all__ = [
    "EdisonSupportNotInstalled",
    "ExternalAnalysisError",
    "ExternalAnalysisProvider",
    "ExternalAnalysisRun",
    "ExternalUploadNotAuthorized",
    "HashMismatchError",
    "InvalidProviderResponse",
    "MissingApiKey",
    "MissingInputError",
    "PromotionAttemptError",
    "ProviderFailure",
    "StudyBundle",
    "StudyBundleManifest",
    "UnsafeUploadError",
    "freeze_study_bundle",
    "get_provider",
    "run_external_analysis",
]
