"""Controlled 2x2: isolate TEXT RICHNESS from the model in the transition-retrieval AUC.

External review (see specs/phase3-match-benchmark/eval-validity.md) flagged that the AUC rose from #423's
~0.56 (ModernBERT-Embed, thin USAspending agreement text, classification framing) to the current ranker's
~0.84-0.88 (TF-IDF, rich abstracts->notices, firm-clustered retrieval) with THREE factors moving at once:
text field, model, and task framing. The gain was therefore unattributed.

This isolates the text axis by holding EVERYTHING else fixed — same firms, same hard negatives, same
TF-IDF model, same firm-clustered retrieval — and varying only how much text each side carries:
    query  : thin = SBIR award TITLES        rich = SBIR ABSTRACTS
    target : thin = NASA project TITLE        rich = NASA project DESCRIPTION
If rich/rich >> thin/thin with the model constant, text richness is a *sufficient* cause and the
ModernBERT->TF-IDF swap is explanatorily unnecessary.

Inputs: data/raw/sbir/award_data.csv and a cached TechPort search JSON (see pull_techport_nasa.py) whose
non-SBIR projects supply firm-linked target text. Model held constant across all four cells by construction.
"""

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

_SUFFIX = re.compile(r"\b(INC|LLC|CORP|CORPORATION|CO|COMPANY|LTD|LP|LLP|THE|INCORPORATED|TECHNOLOGIES|"
                     r"TECHNOLOGY|TECH|SYSTEMS)\b")


def normalize_name(value: object) -> str:
    text = re.sub(r"[^A-Z0-9 ]", " ", str(value).upper())
    return re.sub(r"\s+", " ", _SUFFIX.sub(" ", text)).strip()


def firm_retrieval_auc(query_texts: list[str], target_texts: list[str], *, n_neg: int = 25,
                       seed: int = 0) -> tuple[float, float]:
    """Firm-clustered retrieval AUC + top-1: does firm i's query rank its own target over n_neg others'?

    Pure and model-fixed (TF-IDF). AUC is the mean over firms of P(sim(i,i) > sim(i, random other target)).
    """
    vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=2)
    matrix = vec.fit_transform(list(query_texts) + list(target_texts))
    n = len(query_texts)
    sims = cosine_similarity(matrix[:n], matrix[n:])
    rng = np.random.RandomState(seed)
    aucs, top1 = [], 0
    for i in range(n):
        others = [j for j in range(n) if j != i]
        neg = sims[i, rng.choice(others, min(n_neg, len(others)), replace=False)]
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


def run(award_csv: Path, techport_json: Path) -> dict[str, tuple[float, float]]:
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
    t_title: dict[str, str] = {}
    t_desc: dict[str, str] = {}
    for project in projects:
        if _is_sbir(project):
            continue
        description = str(project.get("description") or "")
        if len(description) < 150:
            continue
        for org in _firm_orgs(project):
            uei = name_to_uei.get(normalize_name(org))
            if uei and uei in q_abstract and len(description) > len(t_desc.get(uei, "")):
                t_desc[uei] = description
                t_title[uei] = str(project.get("title", ""))
    firms = [u for u in t_desc
             if len(q_abstract[u]) > 80 and len(q_title.get(u, "")) > 10 and len(t_title[u]) > 10]

    def cell(qmap: dict, tmap: dict) -> tuple[float, float]:
        return firm_retrieval_auc([qmap[u] for u in firms], [tmap[u] for u in firms])

    return {"firms": len(firms),
            "thin_query/thin_target": cell(q_title, t_title),
            "thin_query/rich_target": cell(q_title, t_desc),
            "rich_query/thin_target": cell(q_abstract, t_title),
            "rich_query/rich_target": cell(q_abstract, t_desc)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--awards", type=Path, default=Path("data/raw/sbir/award_data.csv"))
    parser.add_argument("--techport", type=Path, required=True, help="cached TechPort search JSON")
    args = parser.parse_args(argv)
    result = run(args.awards, args.techport)
    print(f"firms (fixed across all cells): {result['firms']}   model held constant = TF-IDF\n")
    for cell_name in ("thin_query/thin_target", "thin_query/rich_target",
                      "rich_query/thin_target", "rich_query/rich_target"):
        auc, top1 = result[cell_name]
        print(f"  {cell_name:24s} AUC {auc:.3f}  top1 {100 * top1:.0f}%")
    tt = result["thin_query/thin_target"][0]
    rr = result["rich_query/rich_target"][0]
    print(f"\n  text-richness swing (model constant): {tt:.3f} -> {rr:.3f}  (+{rr - tt:.3f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
