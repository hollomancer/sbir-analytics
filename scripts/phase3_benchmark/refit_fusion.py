#!/usr/bin/env python3
"""Refit the transition-ranker fusion ladder on the frozen notice corpus.

Rebuilds the study's ladder (text → +char → +temporal → +id_xref →
+NAICS/notice-type) via the ported GroupKFold-by-firm harness
(``transition_ranker.evaluate``) and reports AUC/top-K per stage against the
published 0.844 [0.800, 0.886]. Emits the ladder JSON and, when the final stage
clears the CI, freezes the fitted logistic coefficients + scaler as a
hash-validated artifact.

Offline given the frozen corpus (``phase3_notice_corpus.parquet``).
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from scripts.phase3_benchmark.notice_matching import normalize_key
from scripts.phase3_benchmark.transition_ranker import (
    NOTICE_TYPE_ORDINAL,
    award_similarity,
    evaluate,
)


# Ladder stages: each adds a feature column to the cumulative matrix.
LADDER: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("text", ("tfidf_word",)),
    ("+char", ("tfidf_word", "tfidf_char")),
    ("+temporal", ("tfidf_word", "tfidf_char", "after_first")),
    ("+id_xref", ("tfidf_word", "tfidf_char", "after_first", "id_cited")),
    (
        "+naics_ntype",
        ("tfidf_word", "tfidf_char", "after_first", "id_cited", "naics_len", "notice_type"),
    ),
)
PUBLISHED_CI = (0.800, 0.886)

_PIID_RE = re.compile(r"\b[A-Z0-9]{4,6}[- ]?\d{2}[- ]?[A-Z][- ]?\d{3,4}\b", re.IGNORECASE)


def _scrub_identity(notice_text: str, firm_name: str) -> str:
    """Remove the cited PIID and the firm's own name words from the notice text.

    Text similarity should reward *technical* overlap, not the notice naming the
    firm or citing the contract number it was attributed by — both are identity
    leakage (the study applied the same scrub as its robustness floor). Scrubbing
    the target side is enough: any residual identity token in the query abstract
    then has nothing to match.
    """

    scrubbed = _PIID_RE.sub(" ", notice_text)
    for word in re.findall(r"[A-Za-z]{4,}", firm_name):
        scrubbed = re.sub(rf"\b{re.escape(word)}\b", " ", scrubbed, flags=re.IGNORECASE)
    return scrubbed


def build_features(corpus: pd.DataFrame) -> pd.DataFrame:
    """Compute the fusion feature columns for every corpus row.

    Text features use identity-scrubbed notice text (PIID + firm name removed),
    so the reported AUC reflects technical matching rather than the notice
    naming the firm — the leakage-controlled number the study freezes on.
    """

    abstracts = corpus["query_abstract"].astype(str).tolist()
    firms = corpus["firm_name"] if "firm_name" in corpus else pd.Series([""] * len(corpus))
    notices = [
        _scrub_identity(str(text), str(firm))
        for text, firm in zip(corpus["notice_text"], firms, strict=True)
    ]
    word = np.diagonal(award_similarity(abstracts, notices, analyzer="word"))
    char = np.diagonal(award_similarity(abstracts, notices, analyzer="char_wb"))

    features = pd.DataFrame(index=corpus.index)
    features["tfidf_word"] = word
    features["tfidf_char"] = char
    # Temporal floor is degenerate on this corpus: recovered notices are
    # post-award by construction, and the frozen corpus does not carry the
    # firm's award years, so `after_first` is a constant. Kept for ladder
    # fidelity; it should add ~nothing (the study saw 0.773 -> 0.779).
    features["after_first"] = 1.0
    features["id_cited"] = (
        corpus.get("match_rule", pd.Series(index=corpus.index)).eq("piid_cite").astype(float)
    )
    features["naics_len"] = corpus["naics_code"].map(lambda v: float(len(normalize_key(v))))
    features["notice_type"] = corpus["notice_type"].map(
        lambda t: NOTICE_TYPE_ORDINAL.get(str(t), 0.0)
    )
    return features


def run_ladder(corpus: pd.DataFrame) -> list[dict[str, object]]:
    features = build_features(corpus)
    labels = corpus["label"].to_numpy()
    groups = corpus["name_key"].to_numpy()
    owners = corpus["owner"].to_numpy()
    results = []
    for name, columns in LADDER:
        matrix = features.loc[:, list(columns)].to_numpy(dtype=float)
        metrics = evaluate(matrix, labels, groups, owners)
        results.append({"stage": name, "features": list(columns), **metrics})
    return results


def freeze_coefficients(corpus: pd.DataFrame, columns: tuple[str, ...], frame_hash: str) -> dict:
    features = build_features(corpus).loc[:, list(columns)].to_numpy(dtype=float)
    labels = corpus["label"].to_numpy()
    scaler = StandardScaler().fit(features)
    model = LogisticRegression(max_iter=1000).fit(scaler.transform(features), labels)
    return {
        "feature_order": list(columns),
        "coefficients": model.coef_[0].tolist(),
        "intercept": float(model.intercept_[0]),
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
        "corpus_frame_hash": frame_hash,
        "frozen_at": datetime.now(UTC).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus", type=Path, default=Path("data/derived/phase3_notice_corpus.parquet")
    )
    parser.add_argument(
        "--manifest", type=Path, default=Path("data/derived/phase3_notice_corpus.manifest.json")
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("specs/phase3-notice-corpus-fusion")
    )
    parser.add_argument(
        "--freeze-to",
        type=Path,
        default=None,
        help="Write coefficients here if the final stage clears the CI.",
    )
    args = parser.parse_args()

    corpus = pd.read_parquet(args.corpus)
    ladder = run_ladder(corpus)
    for stage in ladder:
        print(
            f"{stage['stage']:>14}: AUC {stage['auc']} "
            f"[{stage['ci_low']}, {stage['ci_high']}] top1 {stage['top1']} top3 {stage['top3']} "
            f"(firms {stage['firms']})"
        )
    final = ladder[-1]
    final_auc = float(str(final["auc"]))
    within_ci = PUBLISHED_CI[0] <= final_auc <= PUBLISHED_CI[1]
    print(f"final AUC {final['auc']} within published CI {PUBLISHED_CI}: {within_ci}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "refit_ladder.json").write_text(
        json.dumps(ladder, indent=2), encoding="utf-8"
    )

    if args.freeze_to is not None and within_ci:
        frame_hash = (
            json.loads(args.manifest.read_text()).get("frame_hash", "")
            if args.manifest.exists()
            else ""
        )
        coefficients = freeze_coefficients(corpus, tuple(LADDER[-1][1]), frame_hash)
        args.freeze_to.parent.mkdir(parents=True, exist_ok=True)
        args.freeze_to.write_text(json.dumps(coefficients, indent=2), encoding="utf-8")
        print(f"coefficients frozen -> {args.freeze_to}")
    elif args.freeze_to is not None:
        print("final stage outside the published CI — refusing to freeze coefficients")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
