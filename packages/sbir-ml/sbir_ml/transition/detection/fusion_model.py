"""Load-only fusion-ranker scoring from frozen coefficients.

The award-grain transition-ranker fusion was refit and frozen offline
(``fusion_coefficients.json``; specs/phase3-notice-corpus-fusion) at
leakage-scrubbed AUC 0.847 [0.792, 0.898], reproducing the study's 0.844 within
CI. Production scores with these constants — it never fits — and the loader
refuses a coefficient set whose corpus hash does not match the caller's
expectation, so scores can never silently drift from the corpus they were fit on.

That guarantee only holds when a caller actually states its expectation.
:data:`FROZEN_CORPUS_FRAME_HASH` is that expectation, pinned in code so the
production path can arm the check without reading anything outside the installed
package. It is the frame hash of the award-grain corpus the shipped coefficients
were fit on, and `tests/unit/transition/detection/test_fusion_model.py` asserts
it still matches both the coefficients file and the committed provenance record
(`specs/phase3-notice-corpus-fusion/corpus.manifest.json`) — the corpus parquet
itself is gitignored, so the manifest is the only in-repo witness to what was fit.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


DEFAULT_COEFFICIENTS_PATH = Path(__file__).with_name("fusion_coefficients.json")

#: Frame hash of the award-grain notice corpus the shipped coefficients were fit
#: on (828 rows, 138 positives, 101 firms). Changing the coefficients without
#: changing this constant is the drift this pin exists to stop.
FROZEN_CORPUS_FRAME_HASH = "4c4064f04d04ca2f0c4c96e50ce3be8b6169bfd7ff3d4c51b2a6c804782a7b84"


@dataclass(frozen=True)
class FusionCoefficients:
    """Frozen logistic-fusion weights + standardizer; scores, never fits."""

    feature_order: tuple[str, ...]
    coefficients: tuple[float, ...]
    intercept: float
    scaler_mean: tuple[float, ...]
    scaler_scale: tuple[float, ...]
    corpus_frame_hash: str

    def score(self, features: Sequence[float]) -> float:
        """Fusion probability for one candidate's feature vector."""

        if len(features) != len(self.feature_order):
            raise ValueError(
                f"expected {len(self.feature_order)} features {self.feature_order}, "
                f"got {len(features)}"
            )
        z = self.intercept
        for value, mean, scale, coef in zip(
            features, self.scaler_mean, self.scaler_scale, self.coefficients, strict=True
        ):
            standardized = (value - mean) / scale if scale else 0.0
            z += coef * standardized
        return 1.0 / (1.0 + math.exp(-z))


def load_fusion_coefficients(
    path: str | Path = DEFAULT_COEFFICIENTS_PATH,
    *,
    expected_corpus_hash: str | None = None,
) -> FusionCoefficients:
    """Load frozen coefficients; refuse a corpus-hash mismatch."""

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    corpus_hash = str(data["corpus_frame_hash"])
    if expected_corpus_hash is not None and corpus_hash != expected_corpus_hash:
        raise ValueError(
            "fusion coefficients were fit on a different corpus "
            f"(embedded {corpus_hash!r} != expected {expected_corpus_hash!r})"
        )
    return FusionCoefficients(
        feature_order=tuple(data["feature_order"]),
        coefficients=tuple(float(c) for c in data["coefficients"]),
        intercept=float(data["intercept"]),
        scaler_mean=tuple(float(m) for m in data["scaler_mean"]),
        scaler_scale=tuple(float(s) for s in data["scaler_scale"]),
        corpus_frame_hash=corpus_hash,
    )


__all__ = [
    "FROZEN_CORPUS_FRAME_HASH",
    "FusionCoefficients",
    "load_fusion_coefficients",
]
