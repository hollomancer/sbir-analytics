"""Provisional DoD portfolio-linkage benchmark on coded Phase III contracts.

The positive population is FPDS SR3/ST3 coded and therefore does not represent
uncoded Phase III.  The metric is a same-register linkage proxy, not detector
precision, recall, or a dark-contract count.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from retrieval_metrics import tie_corrected_auc, tie_rate


def floor_coverage(lengths: np.ndarray, thresholds: tuple[int, ...]) -> dict[int, float]:
    """Fraction of targets with description length at least each threshold."""
    n = len(lengths)
    return {t: (round(100 * float((lengths >= t).mean()), 1) if n else 0.0) for t in thresholds}


def _dates(frame: pd.DataFrame, names: tuple[str, ...]) -> pd.Series:
    parsed = [
        pd.to_datetime(frame[name], errors="coerce", utc=True) for name in names if name in frame
    ]
    if not parsed:
        return pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns, UTC]")
    return pd.concat(parsed, axis=1).bfill(axis=1).iloc[:, 0]


def build_asof_pairs(awards: pd.DataFrame, coded: pd.DataFrame) -> pd.DataFrame:
    """Return one row per coded target with only pre-target Phase II text.

    Target description, FY, PSC, action date, and key are copied from the same
    contract row.  No longest-description or firm-level target collapse occurs.
    """
    source = awards.copy()
    source = source[
        (source["UEI"].astype(str).str.len() > 5) & (source["Agency"] == "Department of Defense")
    ]
    phase = source["Phase"].astype(str).str.upper()
    source = source[
        phase.str.contains("II", na=False) & ~phase.str.contains("III", na=False)
    ].copy()
    source["phase_ii_date"] = _dates(source, ("Proposal Award Date", "Award Date", "award_date"))
    if "Solicitation Year" in source:
        year_end = pd.to_datetime(
            source["Solicitation Year"].map(lambda value: f"{value}-12-31"),
            errors="coerce",
            utc=True,
        )
        source["phase_ii_date"] = source["phase_ii_date"].fillna(year_end)
    source = source[
        source["phase_ii_date"].notna() & source["Abstract"].astype(str).str.strip().ne("")
    ]
    by_firm = {
        uei: group.sort_values("phase_ii_date") for uei, group in source.groupby("UEI", sort=False)
    }

    targets = coded.copy()
    targets["target_date"] = _dates(
        targets, ("signed", "signedDate", "action_date", "effectiveDate")
    )
    if "fy" in targets:
        fy_end = pd.to_datetime(
            pd.to_numeric(targets["fy"], errors="coerce").map(
                lambda value: f"{int(value)}-09-30" if pd.notna(value) else None
            ),
            errors="coerce",
            utc=True,
        )
        targets["target_date"] = targets["target_date"].fillna(fy_end)

    rows: list[dict[str, object]] = []
    for index, target in targets.iterrows():
        uei = str(target.get("uei") or target.get("UEI") or "").strip()
        target_date = target["target_date"]
        history = by_firm.get(uei)
        if not uei or history is None or pd.isna(target_date):
            continue
        eligible = history[history["phase_ii_date"] <= target_date]
        if eligible.empty:
            continue
        prior = eligible.iloc[-1]
        description = str(target.get("desc") or target.get("description") or "").strip()
        if not description:
            continue
        source_fy = pd.to_numeric(pd.Series([target.get("fy")]), errors="coerce").iloc[0]
        fiscal_year = (
            int(source_fy)
            if pd.notna(source_fy)
            else int(target_date.year + (1 if target_date.month >= 10 else 0))
        )
        rows.append(
            {
                "target_row": index,
                "target_key": str(
                    target.get("contract_award_unique_key")
                    or target.get("unique_award_key")
                    or target.get("award_key")
                    or index
                ),
                "uei": uei,
                "query": str(prior["Abstract"]),
                "phase_ii_date": prior["phase_ii_date"],
                "target_date": target_date,
                "description": description,
                "fy": fiscal_year,
                "psc": str(target.get("psc") or target.get("productOrServiceCode") or "")[:4],
            }
        )
    return pd.DataFrame(rows)


def within_dod_auc(
    pairs: pd.DataFrame, *, seed: int = 0, min_pool: int = 8, n_neg: int = 25
) -> dict[str, object]:
    """Score coded targets against different-firm coded targets in the same register."""
    required = {"uei", "query", "description", "fy", "psc"}
    missing = sorted(required - set(pairs.columns))
    if missing:
        raise ValueError(f"pairs missing required columns: {missing}")
    if len(pairs) < 2:
        raise ValueError("retrieval evaluation requires at least two targets")

    texts = pairs["query"].astype(str).tolist() + pairs["description"].astype(str).tolist()
    matrix = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1).fit_transform(
        texts
    )
    n = len(pairs)
    sims = cosine_similarity(matrix[:n], matrix[n:])
    rng = np.random.RandomState(seed)
    aucs: list[float] = []
    ties: list[float] = []
    tiers = {"exact_psc_year": 0, "same_psc_relaxed_year": 0, "excluded": 0}
    for i, row in pairs.reset_index(drop=True).iterrows():
        other = [j for j in range(n) if j != i and pairs.iloc[j]["uei"] != row["uei"]]
        same_psc = [j for j in other if pairs.iloc[j]["psc"] == row["psc"] and row["psc"]]
        exact = [j for j in same_psc if abs(int(pairs.iloc[j]["fy"]) - int(row["fy"])) <= 1]
        if len(exact) >= min_pool:
            pool = exact
            tiers["exact_psc_year"] += 1
        elif len(same_psc) >= min_pool:
            pool = same_psc
            tiers["same_psc_relaxed_year"] += 1
        else:
            tiers["excluded"] += 1
            continue
        chosen = rng.choice(pool, min(n_neg, len(pool)), replace=False)
        negatives = sims[i, chosen]
        aucs.append(tie_corrected_auc(float(sims[i, i]), negatives))
        ties.append(tie_rate(float(sims[i, i]), negatives))
    return {
        "status": "provisional",
        "label_semantics": "coded Phase III portfolio-linkage proxy",
        "targets": n,
        "evaluated_targets": len(aucs),
        "negative_tier_counts": tiers,
        "auc": float(np.mean(aucs)) if aucs else None,
        "tie_rate": float(np.mean(ties)) if ties else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--awards", type=Path, default=Path("data/raw/sbir/award_data.csv"))
    parser.add_argument("--coded", type=Path, default=Path("data/derived/m0a_coded_dod.parquet"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if not args.awards.exists() or not args.coded.exists():
        result: dict[str, object] = {
            "status": "blocked_missing_inputs",
            "missing": [str(path) for path in (args.awards, args.coded) if not path.exists()],
        }
    else:
        awards = pd.read_csv(args.awards, dtype=str, keep_default_na=False)
        coded = pd.read_parquet(args.coded)
        pairs = build_asof_pairs(awards, coded)
        result = within_dod_auc(pairs)
        result["description_floor_coverage"] = floor_coverage(
            pairs["description"].str.len().to_numpy(), (40, 150, 515, 900)
        )
    payload = json.dumps(result, indent=2, default=str) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload)
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
