"""Controlled 2x2: isolate TEXT RICHNESS from the model in the transition-retrieval AUC.

External review (see specs/phase3-match-benchmark/eval-validity.md) flagged that the AUC rose from #423's
~0.56 (ModernBERT-Embed, thin USAspending agreement text, classification framing) to the current ranker's
~0.84-0.88 (TF-IDF, rich abstracts->notices, firm-clustered retrieval) with THREE factors moving at once:
text field, model, and task framing. The gain was therefore unattributed.

This isolates the text axis by holding EVERYTHING else fixed — same firms, same negatives, same TF-IDF model,
same firm-clustered retrieval — and varying only how much text each side carries:
    query  : thin = SBIR award TITLES        rich = SBIR ABSTRACTS
    target : thin = NASA project TITLE        rich = NASA project DESCRIPTION

Negative construction (--negatives): `random` (uniform within same register — clean deltas but easy, so
optimistic absolutes) or `metadata` (same NASA technology-taxonomy area + close year, different firm — the
NAICS-analogue hard negative; trustworthy absolutes). All figures are **under TF-IDF** — a lexical model, so
report the scope; the richness gradient may differ under an embedding model.

Inputs: data/raw/sbir/award_data.csv and a cached TechPort search JSON (see pull_techport_nasa.py).
"""

import argparse
import difflib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def longest_shared_word_run(x: str, y: str, cap: int = 400) -> int:
    """Longest contiguous shared word run — the text-reuse / plagiarism probe. Pure.

    If positive (query, own target) pairs share far longer runs than negatives, TF-IDF is detecting copied
    strings, not technical relatedness (a fragile result). Equal distributions mean distributed vocabulary.
    """
    xt, yt = x.lower().split()[:cap], y.lower().split()[:cap]
    return difflib.SequenceMatcher(None, xt, yt, autojunk=False).find_longest_match(
        0, len(xt), 0, len(yt)).size


def paired_bootstrap(per_firm: np.ndarray, n_boot: int = 2000,
                     seed: int = 1) -> tuple[float, float, float]:
    """Firm-clustered bootstrap of a per-firm statistic → (mean, 2.5%, 97.5%). Pure.

    Used on the paired per-firm difference of main effects (random vs metadata negatives): because the same
    firms appear in both conditions, correlated errors cancel and the CI on the difference is tight.
    """
    rng = np.random.RandomState(seed)
    n = len(per_firm)
    means = [per_firm[rng.choice(n, n, replace=True)].mean() for _ in range(n_boot)]
    return float(per_firm.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))

_SUFFIX = re.compile(r"\b(INC|LLC|CORP|CORPORATION|CO|COMPANY|LTD|LP|LLP|THE|INCORPORATED|TECHNOLOGIES|"
                     r"TECHNOLOGY|TECH|SYSTEMS)\b")


def normalize_name(value: object) -> str:
    text = re.sub(r"[^A-Z0-9 ]", " ", str(value).upper())
    return re.sub(r"\s+", " ", _SUFFIX.sub(" ", text)).strip()


def random_negatives(n: int, n_neg: int, seed: int = 0) -> dict[int, np.ndarray]:
    """{firm i: n_neg random other-firm indices}. Same register, representation-independent."""
    rng = np.random.RandomState(seed)
    out = {}
    for i in range(n):
        others = [j for j in range(n) if j != i]
        out[i] = rng.choice(others, min(n_neg, len(others)), replace=False)
    return out


def metadata_hard_negatives(years: np.ndarray, tx_areas: np.ndarray, n_neg: int, seed: int = 0,
                            year_window: int = 2, min_pool: int = 8) -> tuple[dict[int, np.ndarray], int]:
    """Hard negatives matched on metadata, NOT text (so representation-independent and artifact-free).

    Pool for firm i = other firms with the same NASA TX area and |year - year_i| <= window; relax to same-TX
    only if too small; fall back to random if still under min_pool. Returns (neg map, n_true_hard).
    """
    rng = np.random.RandomState(seed)
    n = len(years)
    out, hard = {}, 0
    for i in range(n):
        same_tx = [j for j in range(n) if j != i and tx_areas[j] and tx_areas[j] == tx_areas[i]]
        pool = [j for j in same_tx if abs(years[j] - years[i]) <= year_window]
        if len(pool) < min_pool:
            pool = same_tx
        if len(pool) >= min_pool:
            hard += 1
        else:
            pool = [j for j in range(n) if j != i]
        out[i] = rng.choice(pool, min(n_neg, len(pool)), replace=False)
    return out, hard


def firm_retrieval_auc(query_texts: list[str], target_texts: list[str],
                       neg_indices: dict[int, np.ndarray]) -> tuple[float, float]:
    """Firm-clustered retrieval AUC + top-1 under a FIXED negative set (identical across text conditions).

    AUC = mean over firms of P(sim(i, own target) > sim(i, negative target)). Model = TF-IDF, held constant.
    """
    vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=2)
    matrix = vec.fit_transform(list(query_texts) + list(target_texts))
    n = len(query_texts)
    sims = cosine_similarity(matrix[:n], matrix[n:])
    aucs, top1 = [], 0
    for i in range(n):
        neg = sims[i, neg_indices[i]]
        aucs.append(float((sims[i, i] > neg).mean()))
        top1 += int((neg >= sims[i, i]).sum() == 0)
    return float(np.mean(aucs)), top1 / n


def _firm_orgs(project: dict) -> list[str]:
    orgs = list(project.get("otherOrganizations") or [])
    lead = project.get("leadOrganization")
    if isinstance(lead, dict):
        orgs.append(lead)
    return [o.get("organization_name") or o.get("organizationName") or "" for o in orgs
            if isinstance(o, dict) and o.get("organization_type") == "Industry"]


def _is_sbir(project: dict) -> bool:
    program = project.get("program") or {}
    title = program.get("title", "") if isinstance(program, dict) else str(program)
    return "SMALL BUSINESS" in title.upper() or str(project.get("phase")) in ("1", "2", "2E", "2X", "2S", "3")


def _year(value: object) -> int | None:
    match = re.search(r"(19[89]\d|20[0-2]\d)", str(value))
    return int(match.group()) if match else None


def _tx_area(project: dict) -> str:
    tx = project.get("primaryTx")
    code = tx.get("code", "") if isinstance(tx, dict) else ""
    match = re.match(r"(TX\d+)", code)
    return match.group(1) if match else ""


def run(award_csv: Path, techport_json: Path, *, negatives: str = "random",
        n_neg: int = 25) -> dict[str, object]:
    awards = pd.read_csv(award_csv, dtype=str, keep_default_na=False)
    awards = awards[awards["UEI"].str.len() > 5]
    name_to_uei: dict[str, str] = {}
    for company, uei in zip(awards["Company"], awards["UEI"]):
        key = normalize_name(company)
        if len(key) > 4:
            name_to_uei.setdefault(key, uei)
    q_title = awards.groupby("UEI")["Award Title"].apply(lambda s: " ".join(x for x in s if x)[:2000]).to_dict()
    q_abstract = awards.groupby("UEI")["Abstract"].apply(lambda s: " ".join(x for x in s if x)[:9000]).to_dict()

    listing = json.loads(techport_json.read_text())
    projects = listing.get("results") or listing.get("projects") or listing
    rec: dict[str, dict] = {}
    for project in projects:
        if _is_sbir(project):
            continue
        description = str(project.get("description") or "")
        if len(description) < 150:
            continue
        for org in _firm_orgs(project):
            uei = name_to_uei.get(normalize_name(org))
            if uei and uei in q_abstract and len(description) > len(rec.get(uei, {}).get("desc", "")):
                rec[uei] = {"desc": description, "title": str(project.get("title", "")),
                            "yr": _year(project.get("startDate")) or -999, "tx": _tx_area(project)}
    firms = [u for u in rec
             if len(q_abstract[u]) > 80 and len(q_title.get(u, "")) > 10 and len(rec[u]["title"]) > 10]

    if negatives == "metadata":
        years = np.array([rec[u]["yr"] for u in firms])
        tx_areas = np.array([rec[u]["tx"] for u in firms])
        neg_indices, hard = metadata_hard_negatives(years, tx_areas, n_neg)
    else:
        neg_indices, hard = random_negatives(len(firms), n_neg), len(firms)

    def cell(qmap: dict, tmap: dict) -> tuple[float, float]:
        return firm_retrieval_auc([qmap[u] for u in firms], [tmap[u] for u in firms], neg_indices)

    t_title = {u: rec[u]["title"] for u in firms}
    t_desc = {u: rec[u]["desc"] for u in firms}
    return {"firms": len(firms), "negatives": negatives, "true_hard_neg_firms": hard,
            "thin_query/thin_target": cell(q_title, t_title),
            "thin_query/rich_target": cell(q_title, t_desc),
            "rich_query/thin_target": cell(q_abstract, t_title),
            "rich_query/rich_target": cell(q_abstract, t_desc)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--awards", type=Path, default=Path("data/raw/sbir/award_data.csv"))
    parser.add_argument("--techport", type=Path, required=True, help="cached TechPort search JSON")
    parser.add_argument("--negatives", choices=("random", "metadata"), default="random")
    args = parser.parse_args(argv)
    result = run(args.awards, args.techport, negatives=args.negatives)
    print(f"firms (fixed across all cells): {result['firms']}   model = TF-IDF   "
          f"negatives = {result['negatives']} (true-hard for {result['true_hard_neg_firms']})\n")
    for cell_name in ("thin_query/thin_target", "thin_query/rich_target",
                      "rich_query/thin_target", "rich_query/rich_target"):
        auc, top1 = result[cell_name]
        print(f"  {cell_name:24s} AUC {auc:.3f}  top1 {100 * top1:.0f}%")
    tt = result["thin_query/thin_target"][0]
    tr = result["thin_query/rich_target"][0]
    rt = result["rich_query/thin_target"][0]
    rr = result["rich_query/rich_target"][0]
    print(f"\n  target main effect (avg): +{((tr - tt) + (rr - rt)) / 2:.3f}   "
          f"query main effect (avg): +{((rt - tt) + (rr - tr)) / 2:.3f}   "
          f"interaction: {(rr - rt) - (tr - tt):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
