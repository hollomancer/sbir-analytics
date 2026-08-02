#!/usr/bin/env python3
"""Firm-ranking measurement with non-text lineage features (spec T3, Lever A).

The T6/forward numbers (~0.47) measure CONTRACT-ranking: given a firm, rank the true
transition *contract* (terse text) among decoys. But the packet's real job is
FIRM-ranking: given an opportunity, rank candidate *firms*. That flips which side is
rich — the candidates are firm SBIR abstracts (always rich), so the text-poverty wall
that capped contract-ranking does not apply.

This scores firm-ranking on the frozen fusion text signal, then adds **non-text lineage
features** that are constant within a contract-ranking pool but vary across firms:
agency continuity, prior-award density, and Phase-II timing plausibility. All are
computable at packet time from (firm, opportunity) alone — leakage-safe.

Two decoy modes: ``random`` (diverse firms) and ``hard`` (same-agency-bucket firms, which
neutralizes the agency feature so any lift is density+timing). Self-contained; local only.
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

from sbir_etl.identity import CompanyNameProfile, normalize_company_name


def normalize_name(s: object) -> str:
    return normalize_company_name(s, profile=CompanyNameProfile.ORGANIZATION_KEY_V1)


def firm_bucket(agency: str, branch: str) -> str:
    agency, branch = str(agency).upper(), str(branch).upper()
    if "DEFENSE" in agency:
        for b in ("NAVY", "ARMY", "AIR FORCE"):
            if b in branch:
                return b.replace(" ", "")
        return "DOD"
    for key, tag in (("HEALTH", "HHS"), ("SCIENCE FOUND", "NSF"), ("ENERGY", "DOE"), ("AERONAUT", "NASA")):
        if key in agency:
            return tag
    return agency[:6]


def notice_bucket(dept: str, sub: str) -> str:
    text = f"{dept} {sub}".upper()
    for b in ("NAVY", "ARMY", "AIR FORCE"):
        if b in text:
            return b.replace(" ", "")
    for key, tag in (("HEALTH", "HHS"), ("AERONAUT", "NASA"), ("DEFENSE", "DOD")):
        if key in text:
            return tag
    return text[:6]


def _fusion_text(opp: str, cands: list[str], k: dict) -> np.ndarray:
    wm = TfidfVectorizer(ngram_range=(1, 2), stop_words="english").fit_transform([opp, *cands])
    word = cosine_similarity(wm[0:1], wm[1:]).ravel()
    cm = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5)).fit_transform([opp, *cands])
    char = cosine_similarity(cm[0:1], cm[1:]).ravel()
    return k["cw"] * (word - k["mw"]) / k["sw"] + k["cc"] * (char - k["mc"]) / k["sc"]


def measure(parquet_dir: Path, award_csv: Path, coef_path: Path, *, mode: str = "random", seed: int = 20260802):
    rng = np.random.RandomState(seed)
    c = json.loads(coef_path.read_text())
    k = {"cw": c["coefficients"][0], "cc": c["coefficients"][1], "mw": c["scaler_mean"][0],
         "mc": c["scaler_mean"][1], "sw": c["scaler_scale"][0], "sc": c["scaler_scale"][1]}

    aw = pd.read_csv(award_csv, usecols=["Company", "Agency", "Branch", "Phase", "Award Year", "Abstract"], dtype=str)
    aw["nk"] = aw["Company"].map(normalize_name)
    aw["yr"] = pd.to_numeric(aw["Award Year"], errors="coerce")
    firm = aw.groupby("nk").agg(
        abstract=("Abstract", lambda s: " ".join(s.dropna().astype(str))[:4000]),
        n=("Company", "size"),
        p2=("yr", lambda s: s[aw.loc[s.index, "Phase"].str.contains("II", na=False)].min()),
        buckets=("Agency", lambda s: {firm_bucket(a, b) for a, b in zip(s, aw.loc[s.index, "Branch"], strict=False)}),
    )
    firm = firm[firm["abstract"].str.len() > 150]
    fa = {row.Index: row for row in firm.itertuples()}
    keys = list(fa)
    by_bucket: dict[str, list[str]] = {}
    for key, row in fa.items():
        for b in row.buckets:
            by_bucket.setdefault(b, []).append(key)

    notices = pd.concat([pd.read_parquet(f) for f in glob.glob(str(parquet_dir / "FY*_phase3_selflabeled.parquet"))],
                        ignore_index=True)

    def firm_name(row: dict) -> str:
        awardee = str(row.get("Awardee") or "").strip()
        if len(awardee) > 3:
            return awardee
        m = re.search(r"\bto\s+([A-Za-z][^,]{1,60}),\s+\d", str(row.get("Description") or ""))
        return m.group(1) if m else ""

    def lookup(name: str) -> str | None:
        nk = normalize_name(name)
        if nk in fa:
            return nk
        return next((c for c in keys if nk == c or nk.startswith(c + " ")), None)

    text_res, comb_res = [], []
    for _, r in notices.iterrows():
        true = lookup(firm_name(r.to_dict()))
        opp = str(r.get("Description") or "")
        if not true or len(opp) < 60:
            continue
        ob = notice_bucket(r.get("Department/Ind.Agency"), r.get("Sub-Tier"))
        if mode == "hard":
            src = [d for d in by_bucket.get(ob, []) if d != true]
        else:
            src = [d for d in keys if d != true]
        if len(src) < 9:
            continue
        cand = [true, *rng.choice(src, 9, replace=False)]
        oy = pd.to_numeric(pd.Series([str(r.get("PostedDate"))[:4]]), errors="coerce").iloc[0]
        tsim = _fusion_text(opp, [fa[x].abstract for x in cand], k)
        tz = (tsim - tsim.mean()) / (tsim.std() + 1e-9)
        agency = np.array([1.0 if ob in fa[x].buckets else 0.0 for x in cand])
        dens = np.log1p(np.array([fa[x].n for x in cand]))
        dz = (dens - dens.mean()) / (dens.std() + 1e-9)
        timing = np.array([1.0 if (not np.isnan(fa[x].p2) and not np.isnan(oy) and fa[x].p2 <= oy) else 0.0 for x in cand])
        combined = tz + 1.2 * agency + 0.3 * dz + 0.4 * timing
        for res, score in ((text_res, tsim), (comb_res, combined)):
            order = np.argsort(-score)
            res.append((int(order[0] == 0), int(0 in order[:3])))
    return {
        "mode": mode,
        "n": len(text_res),
        "text_p1": round(np.mean([x[0] for x in text_res]), 3) if text_res else None,
        "text_p3": round(np.mean([x[1] for x in text_res]), 3) if text_res else None,
        "combined_p1": round(np.mean([x[0] for x in comb_res]), 3) if comb_res else None,
        "combined_p3": round(np.mean([x[1] for x in comb_res]), 3) if comb_res else None,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--parquet-dir", type=Path, default=Path("data/derived/phase3_selflabeled"))
    p.add_argument("--award-csv", type=Path, default=Path("data/raw/sbir/award_data.csv"))
    p.add_argument("--coefficients", type=Path,
                   default=Path("packages/sbir-ml/sbir_ml/transition/detection/fusion_coefficients.json"))
    p.add_argument("--mode", choices=["random", "hard"], default="hard")
    args = p.parse_args()
    print("Firm-ranking with non-text lineage features:")
    for key, value in measure(args.parquet_dir, args.award_csv, args.coefficients, mode=args.mode).items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
