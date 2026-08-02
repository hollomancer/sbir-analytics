#!/usr/bin/env python3
"""Emit a precision@K hand-audit sample from the frozen fusion ranker.

Scores every corpus candidate with the *frozen* coefficients (the deployed
path, not a fresh fit), then writes each firm's candidate set ranked by score.
A human adjudicates whether the top-ranked notice is the firm's true transition
— the deployment metric the study left pending.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from sbir_ml.transition.detection.fusion_model import load_fusion_coefficients

from scripts.phase3_benchmark.refit_fusion import build_features


def build_audit(corpus: pd.DataFrame, coefficients_path: Path, top_k: int) -> pd.DataFrame:
    model = load_fusion_coefficients(coefficients_path)
    features = build_features(corpus)[list(model.feature_order)]
    scores = features.apply(lambda row: model.score(row.tolist()), axis=1)
    scored = corpus.assign(fusion_score=scores)

    audits: list[pd.DataFrame] = []
    for _owner, group in scored.groupby("owner", sort=False):
        ranked = group.sort_values("fusion_score", ascending=False).head(top_k).copy()
        ranked["rank"] = range(1, len(ranked) + 1)
        audits.append(ranked)
    columns = [
        "owner",
        "rank",
        "fusion_score",
        "label",
        "firm_name",
        "notice_id",
        "notice_type",
        "office",
        "posted_date",
        "notice_text",
    ]
    out = pd.concat(audits, ignore_index=True) if audits else pd.DataFrame(columns=columns)
    out["notice_text"] = out["notice_text"].astype(str).str.slice(0, 300)
    return out.loc[:, columns]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus", type=Path, default=Path("data/derived/phase3_notice_corpus.parquet")
    )
    parser.add_argument(
        "--coefficients",
        type=Path,
        default=Path("packages/sbir-ml/sbir_ml/transition/detection/fusion_coefficients.json"),
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--output", type=Path, default=Path("reports/phase_iii/audit/fusion_precision_at_k.csv")
    )
    args = parser.parse_args()

    corpus = pd.read_parquet(args.corpus)
    audit = build_audit(corpus, args.coefficients, args.top_k)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(args.output, index=False)

    # precision@1: fraction of *owners* (cited prior awards — the award grain, NOT
    # firms; 138 owners span 101 firms) whose rank-1 candidate is the true notice.
    #
    # IN-SAMPLE: the coefficients were fit on this same corpus, so this number
    # carries no generalization claim. The held-out analogue is the ladder's
    # final-stage out-of-fold top1 in refit_ladder.json.
    owners = audit["owner"].nunique()
    top1_true = int(((audit["rank"] == 1) & (audit["label"] == 1)).sum())
    print(f"audit: {len(audit)} rows across {owners} award-grain owners -> {args.output}")
    print(
        f"precision@1 IN-SAMPLE (rank-1 is the true transition): "
        f"{top1_true}/{owners} = {top1_true / owners:.3f} "
        f"— compare against refit_ladder.json out-of-fold top1, not against the CV AUC"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
