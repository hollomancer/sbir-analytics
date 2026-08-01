"""Score award→target candidate pairs with the frozen fusion ranker.

Applies the frozen coefficients (:mod:`fusion_model`) to a whole run of
candidate pairs, computing the same features the ranker was fit on: run-fitted
word + char TF-IDF cosine (award text ↔ identity-scrubbed target text), the
NAICS-code length, and the notice-type ordinal. Returns a per-pair score used to
**rank a firm's candidate procurements** — the model's validated per-firm-lead
use, not a universe classifier.

**Only the score's within-run ordering is meaningful; its absolute value is
not.** Two properties of this path differ from the fit:

* The TF-IDF idf is refit over whatever pairs the run contains, whereas the
  frozen ``scaler_mean``/``scaler_scale`` were calibrated on the J&A notice
  corpus. Cosine magnitudes are idf-dependent, so the standardized features this
  path produces are not on the corpus's distribution.
* Of the six fitted features, only ``tfidf_word``, ``tfidf_char`` and
  ``notice_type`` really vary here — ``naics_len`` is effectively constant at 6
  for SAM notices, and ``after_first``/``id_cited`` carry zero frozen weight and
  are supplied at their neutral (training-mean) value. The deployed score is
  therefore close to a monotone function of
  ``2.21·z(tfidf_word) − 0.71·z(tfidf_char)`` plus a small notice-type term.

Identity scrubbing mirrors ``refit_fusion._scrub_identity``: the firm's own name
words are removed from the target text before similarity is computed, so the
score rewards technical overlap rather than the notice naming the firm. Skipping
it would inflate both cosines relative to the fit.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from sbir_ml.transition.detection.fusion_model import (
    DEFAULT_COEFFICIENTS_PATH,
    FusionCoefficients,
    load_fusion_coefficients,
)
from sbir_ml.transition.detection.text_similarity import paired_tfidf_cosine


#: Notice-type ordinal, keyed by lowercased notice type. Mirrors the table the
#: ranker was fit with (``scripts/phase3_benchmark/transition_ranker.py``);
#: :func:`_notice_type_ordinal` lowercases before lookup so both spellings work.
NOTICE_TYPE_ORDINAL: dict[str, float] = {
    "justification and approval (j&a)": 3.0,
    "justification": 3.0,
    "special notice": 2.0,
    "presolicitation": 2.0,
    "sources sought": 2.0,
    "solicitation": 2.0,
    "combined synopsis/solicitation": 2.0,
    "award notice": 1.0,
}

#: Features the fit saw as constants. Supplied at their training-mean value so
#: standardization sends them to exactly zero.
PLACEHOLDER_FEATURES = ("after_first", "id_cited")

_FIRM_WORD_RE = re.compile(r"[A-Za-z]{4,}")


def _scrub_identity(target_text: str, firm_name: str) -> str:
    """Remove the firm's own name words from the target text.

    Mirrors the training-side scrub. The PIID half of that scrub is omitted:
    this path has no cited prior-award number to remove, because the pair comes
    from the candidate matcher rather than from a citation.
    """

    if not firm_name:
        return target_text
    scrubbed = target_text
    for word in _FIRM_WORD_RE.findall(firm_name):
        scrubbed = re.sub(rf"\b{re.escape(word)}\b", " ", scrubbed, flags=re.IGNORECASE)
    return scrubbed


def _naics_len(code: object) -> float:
    return float(len("".join(ch for ch in str(code or "").upper() if ch.isalnum())))


def _notice_type_ordinal(value: object) -> float:
    return NOTICE_TYPE_ORDINAL.get(str(value or "").strip().lower(), 0.0)


def _placeholder_values(model: FusionCoefficients) -> dict[str, float]:
    """Neutral (training-mean) value for each placeholder feature.

    Standardizing the training mean yields exactly zero, so a placeholder cannot
    shift the score. A non-zero weight would mean the feature is no longer inert,
    which this path cannot honour — refuse rather than score on a stale
    assumption.
    """

    order = list(model.feature_order)
    values: dict[str, float] = {}
    for name in PLACEHOLDER_FEATURES:
        if name not in order:
            continue
        index = order.index(name)
        if model.coefficients[index] != 0.0:
            raise ValueError(
                f"frozen coefficient for placeholder feature {name!r} is "
                f"{model.coefficients[index]!r}, not 0.0 — this scorer cannot supply a "
                "real value for it, so the fused score would be wrong. Refit, or extend "
                "score_pairs_with_fusion to compute the feature."
            )
        values[name] = float(model.scaler_mean[index])
    return values


def score_pairs_with_fusion(
    award_texts: Sequence[str],
    target_texts: Sequence[str],
    naics_codes: Sequence[object],
    notice_types: Sequence[object],
    *,
    firm_names: Sequence[object] | None = None,
    coefficients_path: str | Path = DEFAULT_COEFFICIENTS_PATH,
) -> list[float]:
    """Frozen-fusion score per (award, target) pair, TF-IDF fitted over the run.

    All sequences are row-aligned. Returns ``[]`` for an empty run. ``firm_names``
    is optional but should be supplied: without it the target text is not
    identity-scrubbed and both cosines are inflated relative to the fit.

    Raises :class:`ValueError` if the sequences disagree in length, or if the
    loaded coefficients put non-zero weight on a placeholder feature (see
    :data:`PLACEHOLDER_FEATURES`).
    """

    n = len(award_texts)
    if not (len(target_texts) == len(naics_codes) == len(notice_types) == n):
        raise ValueError("all input sequences must be the same length")
    if firm_names is not None and len(firm_names) != n:
        raise ValueError("all input sequences must be the same length")
    if n == 0:
        return []

    model = load_fusion_coefficients(coefficients_path)
    neutral = _placeholder_values(model)

    names = ["" for _ in range(n)] if firm_names is None else [str(v or "") for v in firm_names]
    scrubbed = [_scrub_identity(str(t or ""), names[i]) for i, t in enumerate(target_texts)]
    word = paired_tfidf_cosine(award_texts, scrubbed, analyzer="word")
    char = paired_tfidf_cosine(award_texts, scrubbed, analyzer="char_wb")

    scores: list[float] = []
    for i in range(n):
        row: dict[str, float] = {
            "tfidf_word": float(word[i]),
            "tfidf_char": float(char[i]),
            "naics_len": _naics_len(naics_codes[i]),
            "notice_type": _notice_type_ordinal(notice_types[i]),
            **neutral,
        }
        scores.append(model.score([row[name] for name in model.feature_order]))
    return scores


__all__ = ["NOTICE_TYPE_ORDINAL", "PLACEHOLDER_FEATURES", "score_pairs_with_fusion"]
