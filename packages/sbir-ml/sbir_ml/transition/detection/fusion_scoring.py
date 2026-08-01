"""Score award→target candidate pairs with the frozen fusion ranker.

Applies the frozen coefficients (:mod:`fusion_model`) to a whole run of
candidate pairs, computing the same features the ranker was fit on: run-fitted
word + char TF-IDF cosine (award text ↔ target text), the NAICS-code length, and
the notice-type ordinal. Returns a calibrated per-pair score used to **rank a
firm's candidate procurements** — the model's validated per-firm-lead use, not a
universe classifier.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from sbir_ml.transition.detection.fusion_model import (
    DEFAULT_COEFFICIENTS_PATH,
    load_fusion_coefficients,
)
from sbir_ml.transition.detection.text_similarity import paired_tfidf_cosine


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


def _naics_len(code: object) -> float:
    return float(len("".join(ch for ch in str(code or "").upper() if ch.isalnum())))


def _notice_type_ordinal(value: object) -> float:
    return NOTICE_TYPE_ORDINAL.get(str(value or "").strip().lower(), 0.0)


def score_pairs_with_fusion(
    award_texts: Sequence[str],
    target_texts: Sequence[str],
    naics_codes: Sequence[object],
    notice_types: Sequence[object],
    *,
    coefficients_path: str | Path = DEFAULT_COEFFICIENTS_PATH,
) -> list[float]:
    """Frozen-fusion score per (award, target) pair, TF-IDF fitted over the run.

    All sequences are row-aligned. Returns ``[]`` for an empty run. Features
    ``after_first`` and ``id_cited`` are constants here (their frozen weights are
    zero), so they are supplied as zero placeholders in the model's feature order.
    """

    n = len(award_texts)
    if not (len(target_texts) == len(naics_codes) == len(notice_types) == n):
        raise ValueError("all input sequences must be the same length")
    if n == 0:
        return []

    model = load_fusion_coefficients(coefficients_path)
    word = paired_tfidf_cosine(award_texts, target_texts, analyzer="word")
    char = paired_tfidf_cosine(award_texts, target_texts, analyzer="char_wb")
    scores: list[float] = []
    for i in range(n):
        # ``after_first`` and ``id_cited`` carry zero frozen weight — zero here.
        row: dict[str, float] = {
            "tfidf_word": float(word[i]),
            "tfidf_char": float(char[i]),
            "after_first": 0.0,
            "id_cited": 0.0,
            "naics_len": _naics_len(naics_codes[i]),
            "notice_type": _notice_type_ordinal(notice_types[i]),
        }
        scores.append(model.score([row[name] for name in model.feature_order]))
    return scores


__all__ = ["score_pairs_with_fusion"]
