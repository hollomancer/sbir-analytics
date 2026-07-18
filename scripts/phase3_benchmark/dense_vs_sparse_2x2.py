"""Model axis: is the text-richness gradient real, or a TF-IDF artifact? Run the 2x2 under a DENSE model.

The text_richness_2x2 ablation is entirely "under TF-IDF" — a lexical model that mechanically rewards term
overlap, so more text = more match surface. This runs the identical 2x2 (same NASA firms, same seed-0 random
negatives, same four text conditions) under ModernBERT-Embed and compares. The finding: the richness gradient
is largely TF-IDF-specific — a dense model reads meaning from short text, so it starts far higher on thin
text and the richness main effects nearly vanish. Consequences for the §638 story are in eval-validity.md.

REQUIRES a torch + sentence-transformers environment (NOT the repo .venv — those deps are absent there):
    python -m venv .venv-torch && .venv-torch/bin/pip install torch sentence-transformers pandas scikit-learn
    .venv-torch/bin/python dense_vs_sparse_2x2.py --techport <cached_search.json>
On Apple silicon it uses the MPS GPU. The pure retrieval logic mirrors text_richness_2x2.firm_retrieval_auc.
"""

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

_SUFFIX = re.compile(r"\b(INC|LLC|CORP|CORPORATION|CO|COMPANY|LTD|LP|LLP|THE|INCORPORATED|TECHNOLOGIES|"
                     r"TECHNOLOGY|TECH|SYSTEMS)\b")


def normalize_name(value: object) -> str:
    text = re.sub(r"[^A-Z0-9 ]", " ", str(value).upper())
    return re.sub(r"\s+", " ", _SUFFIX.sub(" ", text)).strip()


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


def dense_auc(model, query_texts: list[str], target_texts: list[str],
              neg_indices: dict[int, np.ndarray]) -> tuple[float, float]:
    """Firm-clustered retrieval AUC + top-1 under a dense embedding model, fixed negatives (Nomic prefixes)."""
    q = model.encode(["search_query: " + t for t in query_texts], normalize_embeddings=True, batch_size=32)
    t = model.encode(["search_document: " + t for t in target_texts], normalize_embeddings=True, batch_size=32)
    sims = q @ t.T
    n = len(query_texts)
    aucs, top1 = [], 0
    for i in range(n):
        neg = sims[i, neg_indices[i]]
        aucs.append(float((sims[i, i] > neg).mean()))
        top1 += int((neg >= sims[i, i]).sum() == 0)
    return float(np.mean(aucs)), top1 / n


def main(argv: list[str] | None = None) -> int:
    from sentence_transformers import SentenceTransformer  # local import: torch env only

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--awards", type=Path, default=Path("data/raw/sbir/award_data.csv"))
    parser.add_argument("--techport", type=Path, required=True)
    parser.add_argument("--model", default="nomic-ai/modernbert-embed-base")
    parser.add_argument("--device", default="mps")
    args = parser.parse_args(argv)

    awards = pd.read_csv(args.awards, dtype=str, keep_default_na=False)
    awards = awards[awards["UEI"].str.len() > 5]
    name_to_uei: dict[str, str] = {}
    for company, uei in zip(awards["Company"], awards["UEI"]):
        key = normalize_name(company)
        if len(key) > 4:
            name_to_uei.setdefault(key, uei)
    q_title = awards.groupby("UEI")["Award Title"].apply(lambda s: " ".join(x for x in s if x)[:2000]).to_dict()
    q_abstract = awards.groupby("UEI")["Abstract"].apply(lambda s: " ".join(x for x in s if x)[:8000]).to_dict()

    listing = json.loads(args.techport.read_text())
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
                rec[uei] = {"desc": description[:8000], "title": str(project.get("title", ""))}
    firms = [u for u in rec
             if len(q_abstract[u]) > 80 and len(q_title.get(u, "")) > 10 and len(rec[u]["title"]) > 10]
    n = len(firms)
    rng = np.random.RandomState(0)
    negs = {i: rng.choice([j for j in range(n) if j != i], 25, replace=False) for i in range(n)}

    model = SentenceTransformer(args.model, device=args.device)
    t_title = {u: rec[u]["title"] for u in firms}
    t_desc = {u: rec[u]["desc"] for u in firms}
    print(f"firms {n}   model {args.model}   device {args.device}\n")
    cells = {}
    for name, qmap, tmap in (("thin_query/thin_target", q_title, t_title),
                             ("thin_query/rich_target", q_title, t_desc),
                             ("rich_query/thin_target", q_abstract, t_title),
                             ("rich_query/rich_target", q_abstract, t_desc)):
        auc, top1 = dense_auc(model, [qmap[u] for u in firms], [tmap[u] for u in firms], negs)
        cells[name] = auc
        print(f"  {name:24s} AUC {auc:.3f}  top1 {100 * top1:.0f}%")
    tt, tr = cells["thin_query/thin_target"], cells["thin_query/rich_target"]
    rt, rr = cells["rich_query/thin_target"], cells["rich_query/rich_target"]
    print(f"\n  DENSE: target +{((tr - tt) + (rr - rt)) / 2:.3f}  query +{((rt - tt) + (rr - tr)) / 2:.3f}  "
          f"interaction {(rr - rt) - (tr - tt):+.3f}")
    print("  [TF-IDF same firms/negs: target +0.139  query +0.076 — the richness gradient is TF-IDF-specific]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
