"""Award-level SBIR transition ranker — reusable scoring core.

Retrieval reframe of Phase III detection: given a firm's Phase I/II award, rank its candidate follow-on
funding events (notices) by likelihood of being that firm's transition. The signal that works is
**sparse lexical** (TF-IDF over abstract↔notice — dense embeddings and BM25 both underperform on this
jargon-heavy text) fused with **orthogonal structural features** — the fusion is what beats text alone.

This module holds the pure, testable core: the structural feature functions and the GroupKFold-by-firm
evaluation harness. Award↔notice text similarity (`award_similarity`) is a thin TF-IDF helper; the full
data-recovery pipeline (GSA archive + FPDS pulls) is a documented dependency, not re-homed here.

Findings and validation: `specs/phase3-match-benchmark/transition-ranker.md`.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler

NOTICE_TYPE_ORDINAL: dict[str, float] = {
    "Justification and Approval (J&A)": 3.0,
    "Justification": 3.0,
    "Special Notice": 2.0,
    "Presolicitation": 2.0,
    "Sources Sought": 2.0,
    "Solicitation": 2.0,
    "Combined Synopsis/Solicitation": 2.0,
    "Award Notice": 1.0,
}


def _nkey(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value).upper())


def temporal_features(notice_year: int | None, firm_award_years: Sequence[int]) -> dict[str, float]:
    """Timeline consistency of a notice with a firm's SBIR activity.

    A transition (a) cannot predate the firm's earliest SBIR award, and (b) may occur during an award's
    period of performance or long after — measured transition lag is median ~6y with a tail to 15-20y,
    so `gap` is a **continuous, unbounded** feature (NO short upper window). Anchored on the firm's
    *earliest* award so a Phase I → Phase III (no Phase II) transition is captured.
    """
    years = [y for y in firm_award_years if y is not None]
    if notice_year is None or not years:
        return {"gap": 0.0, "after_first": 0.5}
    return {"gap": float(notice_year - max(years)), "after_first": 1.0 if notice_year >= min(years) else 0.0}


def id_xref(notice_text: str, firm_identifiers: set[str]) -> float:
    """1.0 iff the notice cites one of the firm's SBIR identifiers (contract#/topic/solicitation#)."""
    haystack = _nkey(notice_text)
    return 1.0 if any(ident in haystack for ident in firm_identifiers if len(ident) >= 6) else 0.0


def notice_type_ordinal(base_type: str) -> float:
    """J&A/Justification (3) > presol/special/solicitation (2) > award notice (1) > other (0)."""
    return NOTICE_TYPE_ORDINAL.get(base_type, 0.0)


def award_similarity(query_texts: Sequence[str], notice_texts: Sequence[str],
                     analyzer: str = "word") -> np.ndarray:
    """Max abstract↔notice TF-IDF cosine per (query, notice). word (1,2)-grams or char_wb (3,5)."""
    ngram = (1, 2) if analyzer == "word" else (3, 5)
    stop = {"stop_words": "english"} if analyzer == "word" else {}
    vec = TfidfVectorizer(analyzer=analyzer, ngram_range=ngram, min_df=1, **stop)
    matrix = vec.fit_transform(list(query_texts) + list(notice_texts))
    q, n = matrix[: len(query_texts)], matrix[len(query_texts):]
    return cosine_similarity(q, n)


def evaluate(features: np.ndarray, labels: np.ndarray, groups: np.ndarray,
             owners: np.ndarray, n_splits: int = 5, seed: int = 20260716) -> dict[str, float]:
    """GroupKFold-BY-FIRM logistic LTR; firm-clustered retrieval AUC + top-K. `owners` groups the rows
    of one candidate set (one true + hard negatives). No firm appears in train and test."""
    per_firm: dict[str, list[float]] = {}
    ranks: list[int] = []
    gkf = GroupKFold(n_splits=min(n_splits, len(set(groups))))
    for train, test in gkf.split(features, labels, groups):
        scaler = StandardScaler().fit(features[train])
        model = LogisticRegression(max_iter=1000).fit(scaler.transform(features[train]), labels[train])
        scored = model.predict_proba(scaler.transform(features[test]))[:, 1]
        for owner in np.unique(owners[test]):
            mask = owners[test] == owner
            lab = labels[test][mask]
            if lab.sum() != 1:
                continue
            true_score = scored[mask][lab == 1][0]
            neg_scores = scored[mask][lab == 0]
            per_firm.setdefault(str(groups[test][mask][0]), []).append(float((true_score > neg_scores).mean()))
            ranks.append(1 + int((neg_scores >= true_score).sum()))
    firm_auc = np.array([np.mean(v) for v in per_firm.values()])
    ranks_arr = np.array(ranks)
    boot = [np.random.default_rng(k).choice(firm_auc, len(firm_auc), replace=True).mean()
            for k in range(2000)] if len(firm_auc) > 1 else [float("nan")]
    return {
        "firms": len(firm_auc),
        "auc": round(float(firm_auc.mean()), 3),
        "ci_low": round(float(np.percentile(boot, 2.5)), 3),
        "ci_high": round(float(np.percentile(boot, 97.5)), 3),
        "top1": round(float((ranks_arr == 1).mean()), 3) if len(ranks_arr) else float("nan"),
        "top3": round(float((ranks_arr <= 3).mean()), 3) if len(ranks_arr) else float("nan"),
    }


__all__ = ["temporal_features", "id_xref", "notice_type_ordinal", "award_similarity", "evaluate",
           "NOTICE_TYPE_ORDINAL"]
