"""The actual within-DoD retrieval number (not a NASA extrapolation), plus the §638 floor and mechanism test.

Provenance caveat, stated first: the positive set (`m0a_coded_dod`, FPDS element-10Q SR3/ST3) IS the
CODED population. The claim is about the UNCODED (dark) Phase III. So every AUC here is an **upper bound on
the population we cannot sample** — if minimal data entry correlates across fields, uncoded Phase IIIs are
even emptier and the detector does worse in the wild.

Three DoD-native reads:
  1. within-DoD retrieval: rich query (Phase II abstract) -> thin target (Phase III `desc`), metadata-hard
     negatives (same PSC + FY, different firm). The real operating number.
  2. §638 floor: what fraction of DoD Phase III descriptions clear each length threshold — the drafting number.
  3. mechanism test: does description emptiness correlate with sparsity in OTHER fields (NAICS/PSC/IDV)?
     If yes, one "minimal CO entry" cause; if no, the description is simply an unenforced optional field.
"""

import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def floor_coverage(lengths: np.ndarray, thresholds: tuple[int, ...]) -> dict[int, float]:
    """Fraction of targets with description length >= each threshold. Pure — the §638 drafting table."""
    n = len(lengths)
    return {t: (round(100 * float((lengths >= t).mean()), 1) if n else 0.0) for t in thresholds}


def _year(value: object) -> int:
    match = re.search(r"(20[0-2]\d)", str(value))
    return int(match.group()) if match else -999


def within_dod_auc(p2_abstract: dict[str, str], targets: dict[str, dict],
                   firms: list[str], seed: int = 0) -> float:
    """Firm-clustered retrieval AUC, rich Phase II abstract -> Phase III desc, metadata-hard negatives."""
    fy = np.array([_year(targets[u]["fy"]) for u in firms])
    psc = np.array([str(targets[u]["psc"])[:4] for u in firms])
    queries = [p2_abstract[u] for u in firms]
    tgt_text = [str(targets[u]["desc"]) for u in firms]
    matrix = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1).fit_transform(queries + tgt_text)
    n = len(firms)
    sims = cosine_similarity(matrix[:n], matrix[n:])
    rng = np.random.RandomState(seed)
    aucs = []
    for i in range(n):
        pool = [j for j in range(n) if j != i and psc[j] == psc[i] and abs(fy[j] - fy[i]) <= 1]
        if len(pool) < 8:
            pool = [j for j in range(n) if j != i]
        neg = sims[i, rng.choice(pool, min(25, len(pool)), replace=False)]
        aucs.append(float((sims[i, i] > neg).mean()))
    return float(np.mean(aucs))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--awards", type=Path, default=Path("data/raw/sbir/award_data.csv"))
    parser.add_argument("--coded", type=Path, default=Path("data/derived/m0a_coded_dod.parquet"))
    args = parser.parse_args(argv)

    coded = pd.read_parquet(args.coded)
    print(f"PROVENANCE: positives are FPDS-coded {dict(coded['research'].value_counts())} "
          f"— the eval population is the COMPLEMENT of the (uncoded) claim. Every AUC below is an upper bound.\n")

    coded["dl"] = coded["desc"].astype(str).str.len()
    print("§638 floor — DoD Phase III descriptions clearing each length (NASA step: 40c~0.66, 150c~0.81, 900c~0.89):")
    for thr, pct in floor_coverage(coded["dl"].to_numpy(), (40, 150, 515, 900)).items():
        print(f"  >= {thr:4d} chars: {pct}%")
    print("  -> a 150-char mandate buys the bottom of the step; the plateau needs ~900 chars, which 0% now meet.\n")

    short, rich = coded["dl"] < 50, coded["dl"] >= 150
    print("mechanism test — missing OTHER fields by description length (is emptiness a common-cause of sloppiness?):")
    for col in ("naics", "psc", "idv_piid"):
        miss = coded[col].astype(str).str.strip().isin(["", "None", "nan", "0"])
        print(f"  {col:9s} missing: short-desc {100 * miss[short].mean():.1f}%  rich-desc {100 * miss[rich].mean():.1f}%")
    print("  -> NAICS/PSC ~always present (enforced); only the free-text description is empty. Not CO sloppiness"
          " — an UNENFORCED optional field. §638 ask: make description mandatory like the codes already are.\n")

    awards = pd.read_csv(args.awards, dtype=str, keep_default_na=False)
    awards = awards[(awards["UEI"].str.len() > 5) & (awards["Agency"] == "Department of Defense")]
    phase2 = awards[awards["Phase"].str.contains("II", na=False) & ~awards["Phase"].str.contains("III", na=False)]
    p2_abstract = phase2.groupby("UEI")["Abstract"].apply(lambda s: " ".join(x for x in s if x)[:9000]).to_dict()
    targets = coded.groupby("uei").agg(desc=("desc", lambda s: max(s, key=len)),
                                       fy=("fy", "first"), psc=("psc", "first")).to_dict("index")
    firms = [u for u in targets if u in p2_abstract and len(p2_abstract[u]) > 80]
    lengths = np.array([len(str(targets[u]["desc"])) for u in firms])
    print(f"WITHIN-DoD retrieval (rich Phase II abstract -> Phase III desc, metadata-hard neg) — the real number:")
    print(f"  all positives (thin target, median {np.median(lengths):.0f}c): AUC "
          f"{within_dod_auc(p2_abstract, targets, firms):.3f}  n={len(firms)}")
    rich_firms = [u for u, ln in zip(firms, lengths) if ln >= 515]
    if len(rich_firms) >= 10:
        print(f"  rich-desc subset (>=515c): AUC {within_dod_auc(p2_abstract, targets, rich_firms):.3f}  n={len(rich_firms)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
