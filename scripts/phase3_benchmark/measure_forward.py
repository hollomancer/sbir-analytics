#!/usr/bin/env python3
"""Forward-representative measurement of the frozen Phase III detector.

The T6 number (~0.467) is the RETROSPECTIVE task: rank a past transition *contract*
(terse FPDS text) among decoys. The packet's real job is FORWARD: rank a firm against
an open *solicitation* — government-written notice text, not a terse contract stub.

This scores the frozen fusion detector on that forward-grain substrate: query = firm's
SBIR Phase I/II abstract; candidate = the government-written text of a self-labeled
SBIR Phase III notice naming that firm (from the SAM Contract Opportunities bulk extract,
materialized under data/derived/phase3_selflabeled); decoys = other such notices. It
answers the open "forward might be higher than 0.467" question with a real number.

Self-contained: inlines the small helpers so it doesn't depend on the unmerged
ground-truth (#481) / coverage (#485) branches; uses only the fusion coefficients merged
to main (#467).
"""

from __future__ import annotations

import argparse
import glob
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

_SUFFIX = re.compile(
    r"\b(INC|INCORPORATED|LLC|L\.?L\.?C|CORP|CORPORATION|CO|COMPANY|LTD|LP|LLP|PC|PLLC)\b\.?",
    re.IGNORECASE,
)
_NON_ALNUM = re.compile(r"[^A-Z0-9 ]")
# firm named in a pre-award intent Description: "...to <FIRM>, <street-number> <addr>"
_AWARD_TO = re.compile(
    r"\bto\s+([A-Za-z][^,]{1,60}(?:,\s*(?:inc|l\.?l\.?c|llc|corp\w*|co|company|ltd|lp)\.?)?),\s+\d{1,6}\s",
    re.IGNORECASE,
)


def normalize_name(name: object) -> str:
    text = _SUFFIX.sub(" ", str(name or "").upper())
    return " ".join(_NON_ALNUM.sub(" ", text).split())


def firm_from_row(row: dict) -> str:
    awardee = str(row.get("Awardee") or "").strip()
    if len(awardee) > 3:
        return awardee
    match = _AWARD_TO.search(str(row.get("Description") or ""))
    if match:
        firm = match.group(1).strip(" ,-\t")
        if 3 < len(firm) < 70 and "sbir" not in firm.lower():
            return firm
    return ""


def load_coefficients(path: Path) -> dict:
    coef = json.loads(path.read_text())
    return {
        "cw": coef["coefficients"][0],
        "cc": coef["coefficients"][1],
        "mw": coef["scaler_mean"][0],
        "mc": coef["scaler_mean"][1],
        "sw": coef["scaler_scale"][0],
        "sc": coef["scaler_scale"][1],
    }


def fusion_order(query: str, candidates: list[str], k: dict) -> np.ndarray:
    """Rank candidates by the frozen fusion (word + char TF-IDF cosine terms)."""

    wm = TfidfVectorizer(ngram_range=(1, 2), stop_words="english").fit_transform([query, *candidates])
    word = cosine_similarity(wm[0:1], wm[1:]).ravel()
    cm = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5)).fit_transform([query, *candidates])
    char = cosine_similarity(cm[0:1], cm[1:]).ravel()
    score = k["cw"] * (word - k["mw"]) / k["sw"] + k["cc"] * (char - k["mc"]) / k["sc"]
    return np.argsort(-score)


def measure(parquet_dir: Path, award_csv: Path, coef_path: Path, *, k_decoys: int = 9, seed: int = 20260802):
    rng = np.random.RandomState(seed)
    coef = load_coefficients(coef_path)

    frames = [pd.read_parquet(f) for f in glob.glob(str(parquet_dir / "FY*_phase3_selflabeled.parquet"))]
    notices = pd.concat(frames, ignore_index=True)
    notices["firm"] = notices.apply(lambda r: firm_from_row(r.to_dict()), axis=1)
    notices = notices[(notices["firm"].str.len() > 3) & (notices["Description"].fillna("").str.len() > 60)]
    notices["nk"] = notices["firm"].map(normalize_name)

    awards = pd.read_csv(award_csv, usecols=["Company", "Phase", "Abstract"], dtype=str)
    awards["nk"] = awards["Company"].map(normalize_name)
    p2 = awards[awards["Phase"].str.contains("II", na=False)].dropna(subset=["Abstract"])
    abstract = p2.groupby("nk")["Abstract"].apply(lambda s: " ".join(s.astype(str))[:4000]).to_dict()
    # SAM Awardee carries trailing address junk ("<FIRM> <CITY> <ST> <ZIP> US"); match the
    # company name-key as a prefix of the notice key (exact, else longest prefix).
    keys_by_first = {}
    for key in abstract:
        keys_by_first.setdefault(key.split(" ", 1)[0], []).append(key)

    def lookup(nk: str) -> str | None:
        if nk in abstract:
            return abstract[nk]
        best = None
        for cand in keys_by_first.get(nk.split(" ", 1)[0], []):
            if (nk == cand or nk.startswith(cand + " ")) and (best is None or len(cand) > len(best)):
                best = cand
        return abstract[best] if best else None

    pool = notices["Description"].astype(str).tolist()
    rows = []
    for _, r in notices.iterrows():
        q = lookup(r["nk"])
        if not q or len(q) < 120:
            continue
        true_text = str(r["Description"])
        others = [d for d in pool if d != true_text]
        decoys = list(rng.choice(others, size=min(k_decoys, len(others)), replace=False))
        order = fusion_order(q, [true_text, *decoys], coef)
        rows.append({"firm": r["firm"], "p1": int(order[0] == 0), "p3": int(0 in order[:3])})
    scored = pd.DataFrame(rows)
    return {
        "n": len(scored),
        "p_at_1": round(scored["p1"].mean(), 3) if len(scored) else None,
        "p_at_3": round(scored["p3"].mean(), 3) if len(scored) else None,
        "retrospective_baseline_p1": 0.467,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parquet-dir", type=Path, default=Path("data/derived/phase3_selflabeled"))
    parser.add_argument("--award-csv", type=Path, default=Path("data/raw/sbir/award_data.csv"))
    parser.add_argument(
        "--coefficients",
        type=Path,
        default=Path("packages/sbir-ml/sbir_ml/transition/detection/fusion_coefficients.json"),
    )
    args = parser.parse_args()
    result = measure(args.parquet_dir, args.award_csv, args.coefficients)
    print("Forward-representative measurement (frozen detector on SAM notice text):")
    for key, value in result.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
